---
state: ready
# RELEASE REFINEMENT 2026-09-10: included in approved 0.6 audit-packet scope.
# IMPLEMENTATION APPROVED 2026-09-10: the user's packet approval readies this
# prerequisite; normal pre-dispatch refinement and factory gates still apply.
# The release section below supersedes historical storage identity/safety
# assumptions; historical provenance remains unedited. No live collector changed.
fixes:
  - feedback/pr-3-typed-attestation-artifacts-declared-and-collected-at-the-gate-boundary
  - feedback/the-platform-has-no-attestation-surface-so-every-target-repo-will-invent-its-own
# DRAFTED 2026-09-03 by the operator session, against ergane-buildout at 238b494.
# Every `file:line` in spec.md and plan.md was read from that commit and verified
# to resolve to the symbol named, not recalled. Three of this spec's anchors had
# ALREADY MOVED between the hand-over's reading and today's — see plan.md.
#
# WHERE THIS CAME FROM. PR-3 and N54 of the `ergane-web` consolidated hand-over.
# The operator's own framing, and it is the right one: "we need a way to visualize
# all of the CI steps, SBOM is another. this is something that you should show but
# we should provide feedback to ergane to support at the platform level."
#
# THE PANE'S JOB IS TO SHOW; THE PLATFORM'S JOB IS TO CARRY. A per-repo gate that
# emits a coverage file is a workaround. Every target repository would invent a
# different one, with a different path, a different format and no reader — and an
# SBOM formatted differently per repo cannot answer "which of my epics shipped
# this dependency", which is the only question an SBOM is for.
#
# THE CONSUMER ALREADY BUILT THE PRODUCER HALF, DELIBERATELY SHAPED SO THIS SPEC
# CAN TAKE IT UNCHANGED. Three of their stories emit the STANDARD artifact at a
# STABLE path — Cobertura `coverage.xml`, vitest JSON, audit JSON — and that
# spec's own Out-of-scope forbids anything in their pane from reading them. They
# are sitting there waiting for a collector. The acceptance criterion worth aiming
# at is that those files are captured with no change to the target repository.
#
# WHY THE PLATFORM AND NOT EACH REPO. A reader must exist or nothing can display
# it; the gate boundary already captures four gates, so an artifact is one more
# capture at a place that exists; and typed rather than opaque-only, because a
# consumer that must sniff the format has per-repo fragmentation back. `opaque`
# is present so an unrecognised artifact is still carried and still attributable.
#
# NOT IN SCOPE. This spec does not admit an artifact into the judge's prompt —
# that is spec territory gated on a constitutional decision about what the judge
# may see, and it is deliberately left alone. It does not parse or interpret an
# artifact's contents. And it does not repurpose `expected_artifacts` /
# `artifacts_present`, which are the anti-rubber-stamp check for read-scope nodes
# and are a decoy with the right name — see plan.md trap 1.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at 602a92c.
# All ten anchors still resolved — 057's four landings touched no file this trio
# cites — but one INSTRUCTION WAS WRONG and would have been built: the plan told
# the implementer to hang the declaration on `VerificationConfig`, which is the
# retry-ladder configuration. The class that carries `gates`, `timeouts` and
# `writes` is `FactoryConfig` (`factory/verify/models.py:291` — `FactoryConfig`).
# Corrected, and kept as a trap.
#
# THREE MECHANISMS WERE READ THIS TIME THAT THE DRAFT HAD NOT READ, and each one
# changes a requirement. (1) `writes:` is a per-gate BOOLEAN, not a path
# allow-list, so US2 is an exemption for a named path and not a list insertion.
# (2) The worktree watch never sees a git-ignored path, so a US2 scenario written
# over an ignored artifact would pass with no production code at all — the
# scenarios now name an unignored path, and collection reads the file from disk
# rather than from the watch. (3) The declaration reaches the gate runner through
# a JSON candidate acceptance whose reader is a named allow-list, so a field
# added to `FactoryConfig` alone is parsed, emitted and never read — 084's own
# FR-012 lesson, now FR-014 here.
#
# STORAGE IS NOW SETTLED, because trap 3 said it had to be before tasks were
# written. The bytes are copied at the boundary to a destination the workflow
# composes and passes in; the record carries a reference, not the bytes, because
# `GateResult` crosses a Temporal activity boundary and an SBOM on that payload is
# an outage. The field 144 will cite is `GateResult.artifacts`, a tuple of
# `GateArtifact`. No new runtime-root resolver is introduced, so this spec does
# not depend on 129.
#
# FIXES AUDIT. Both keys re-read from the ledger: they are one capability asked
# for twice (PR-3 and N54), both open, both `info`. PR-3's acceptance sentence —
# "a repo declaring a coverage path and type gets that file captured on every
# attempt and readable per attempt afterwards, and a repo declaring nothing
# behaves exactly as today" — is FR-006 plus FR-010 plus FR-003. N54's surviving
# half — "one reader or none, never one per repo" — is FR-010. Both stay.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): storage settlement overturned and
# re-settled activity-side, US2's per-path exemption given the control that pins
# it, US3 split at the carriage seam into a new US5, one mis-cited anchor
# corrected, two equality clauses made provable, and the judge assembler named.
#
# THE STORAGE PARAGRAPH ABOVE IS OVERTURNED IN ONE HALF AND KEPT IN THE OTHER.
# Kept: the bytes never travel on `GateResult`, and the field 144 will cite is
# still `GateResult.artifacts`, a tuple of `GateArtifact`. Overturned: "a
# destination the workflow composes". `_verify`
# (`factory/workgraph/workflow.py:2601` — `_verify`) is Temporal workflow code and
# may read neither environment nor filesystem, and `EpicInput`
# (`factory/workgraph/workflow.py:532` — `EpicInput`) carries no runtime root, so
# the only paths it could have composed were a worktree-relative one (destroyed
# with the worktree, defeating the spec while every scenario stayed green) or a
# hardcoded `.ergane` under the target clone
# (wrong under an override, and forbidden by `worktree_path`'s own docstring).
# The destination is now resolved and composed IN THE GATE-RUNNING ACTIVITY,
# through the resolver the engine already has, exactly as `_store_path`
# (`factory/activities/verify_activities.py:634` — `_store_path`) and
# `factory_root` (`factory/activities/agent_activities.py:188` — `factory_root`)
# already do. Still no new resolver, so still no dependency on 129 — FR-017 only
# requires the absolute path 129 will make unconditional.
#
# ANCHOR COUNT, CORRECTED. The REFINED block's "all ten anchors" was the DRAFT's
# count and understates this trio several-fold. The measured count lives in
# plan.md's header, which is the document a future refiner re-reads from, and it
# is stated there once so there is no second copy to rot. One anchor in the block
# above was also mis-cited: `worktree_writes` is
# `factory/verify/models.py:405` — `GateResult`, not `:403`, which is
# `output_tail`. Two reasons the symbol tier could not catch it, and both matter
# to whoever writes the next citation: both lines sit inside `GateResult`, so the
# span check is satisfied either way — and `_check_symbol_anchors` strips this
# frontmatter block before it looks at anything, so no citation written here is
# machine-checked at all. Cite in the body when you want the check.
#
# WHAT THE SPLIT DID. US3 owned five production files and eight scenarios and had
# no margin against the 64 KiB refusal (`factory/verify/diffbounds.py:47`, D-050)
# before the destination plumbing was added to it. It is cut at the seam it
# already had: US3 keeps collection (`factory/verify/models.py`,
# `factory/verify/gates.py`), and a NEW US5 takes carriage — the destination's
# origin, the identity on the activity input, and persistence. Story numbers are
# immutable: nothing is renumbered, US4 keeps its number and now merges after US5.
#
# WHAT IT COST, MEASURED. The round-2 `ergane-web` hand-over that filed both of
# these keys reports 54 operator interventions across 20 landed stories, and the
# reporter's own severity on N54 is `critical` — the highest thing they filed in
# the feedback lane. The cost is legible in what that consumer did instead of
# waiting: it built the producer half itself, three gates emitting Cobertura
# `coverage.xml`, vitest JSON and audit JSON at stable standard paths on every
# attempt, and was then forbidden by its own constitution from reading the three
# files it had just written, because reading them would be inventing the per-repo
# answer this gap forces. Three artifacts written on every attempt, at known
# paths, and read by nothing — that is the measured price of the platform having
# no place to put them.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the "outside the target clone" half
# of FR-017 and US5-S1 struck as unsatisfiable on the deployment that will build
# this spec; the manifest key spelled `artifacts:` in the requirements instead of
# left to an implementer; US5-S2's Then worded over the input `_verify` actually
# constructs rather than over `RunGatesInput`'s field list; `ArtifactType` given a
# single owning story; and the `caches:` reader's inverted path bound named where
# US1's reader is modelled on it.
#
# THE DESTINATION CLAUSE IS CORRECTED, AND THE ENTRY ABOVE IS WRONG WHERE IT
# CITES A DOCSTRING. That entry says a hardcoded `.ergane` under the target clone
# is "forbidden by `worktree_path`'s own docstring". Measured today:
# `scripts/ergane-env.sh` emits `ERGANE_ROOT=$HOME/code/ergane/.factory`, and the
# target repository for this factory's own epics is `/home/admin/code/ergane` — so
# the runtime root is *inside* the target clone, and so is every node worktree
# (`.factory/worktrees/<epic>/<node>`). `worktree_path`'s "Never inside the target
# clone" means "never inside a checkout whose diff is scored", not a path-prefix
# rule; the root is git-ignored (`.gitignore:17-18`), which is what keeps it out
# of the diff check. The hardcode is still wrong for the two reasons that survive
# — it ignores an `ERGANE_ROOT` / `FACTORY_ROOT` override, and it ignores the
# legacy `.factory` root this host is actually running — and those are now the
# whole of trap 7. FR-017 and US5-S1 no longer ask for a property the engine
# cannot produce and the gate-running activity has no argument with which to
# check it: `RunGatesInput` carries no target-repository path at all.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the stale compiled `workgraph.json`
# in this directory escalated from a note to a MUST — measured against the file,
# it carries four nodes, no US5 and no FR-012..FR-019, and `ergane build start`
# loads it off disk without re-deriving; this pass may not delete it, so plan.md
# § Sizing now names the deletion as an operator action and § Verification repeats
# it before its first step, with the D-025 misreading ("never hand-edited" is not
# a reason to leave a stale one) and the "five missing keys" undercount corrected.
# One instruction was wrong and is fixed, and the STORAGE paragraph above states
# it too ("exactly as `_store_path` and `factory_root` already do") — that half of
# it is hereby withdrawn, and the paragraph is left standing because provenance is
# appended to and not rewritten. plan.md claimed both activities resolve
# the host root "through the one engine resolver", but `_store_path`
# (`factory/activities/verify_activities.py:634` — `_store_path`) reaches
# `resolve_env_path` (`factory/env.py:47` — `resolve_env_path`) and a hardcoded
# `.factory/verification.db`, never `resolve_factory_root` — so an implementer
# sent to compose the destination "beside `_store_path`" and told to read it found
# the fifth-resolver pattern trap 7 forbids. Trap 7 and T041 now say to take the
# site from `_store_path` and the resolver from `factory_root`. Five citations
# that had dropped their ` — `symbol`` suffix carry it again, and plan.md's anchor
# counts are re-measured. No requirement, scenario, story or `fixes:` key changed.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): the declared path is now required to
# be CARRIED in one spelling, not merely refused when it escapes — FR-012 gains the
# normalisation clause, US1 gains scenario 8 and tasks.md gains its test, and plan.md
# trap 3 names why. Measured: `changes_between`
# (`factory/verify/worktree_snapshot.py:100` — `changes_between`) fills
# `worktree_writes` from `git diff-tree -r --name-only -z`, so the paths US2 subtracts
# against are git's own normalised spelling, and the subtraction at
# `factory/verify/gates.py:1629` — `_to_result` is string equality. A manifest
# declaring `./coverage.xml` parsed, collected correctly and still demoted its gate
# for writing the artifact it declared — the self-defeat US2 exists to prevent,
# reachable through a spelling. The stale compiled `workgraph.json` this directory
# carries was RE-MEASURED and is unchanged and still a blocking hazard at flip time
# (four nodes, no US5, requirement keys stopping at FR-011, untracked and not
# git-ignored); this pass may not delete it either, so plan.md § Sizing and
# § Verification still carry the operator instruction and nothing about it moved.
---

# Feature Specification: a gate declares the artifact it writes and the platform carries it

**Created**: 2026-09-03
**Depends on**: nothing.

## 0.6 packet dependency refinement (2026-09-10)

The user explicitly included story/spec packets in 0.6. This spec owns reusable
gate-artifact capture; 167 consumes it rather than writing a second collector.
Capture must be safe at the first read, immutable across redispatches and honest
about whether a file was actually produced during this gate. Lexical path
validation alone cannot protect the activity from an escaping symlink or FIFO.
The historical examples naming only epic/node/attempt describe a namespace
prefix, not a unique artifact identity: dispatch and capture identity are now
required for new persisted captures (FR-020 through FR-023).

## The gap, stated precisely

1. A manifest can declare a gate's **command** and nothing else about it.
   `_read_gates` (`factory/verify/factory_yaml.py:340` — `_read_gates`) requires
   each gate's value to be a non-empty string, so there is no place on a gate to
   hang a path or a type.
2. What survives a gate is its exit code, its duration and the last ≤32 KiB of
   its output. `GateResult` (`factory/verify/models.py:374` — `GateResult`) has
   nine fields and not one of them is a file the gate wrote.
3. The one field that names files names them and throws them away.
   `worktree_writes` (`factory/verify/models.py:417` — `GateResult`) is a tuple
   of paths, recorded so that a gate which dirtied the judge's evidence can be
   demoted — never so that anything reads what is at those paths.
4. So a coverage report, a dependency inventory, a scan result or an SBOM is
   written inside the node worktree, is read by nothing, and is destroyed with
   the worktree. The gate boundary already captures four gates per attempt; an
   artifact would be one more capture at a place that exists.
5. The consequence is not that the data is missing. It is that **every target
   repository invents its own answer** and no reader exists for any of them. One
   consumer has already emitted three artifacts at stable standard paths and then
   been forbidden by its own constitution from reading them, because reading them
   would be inventing the per-repo answer this gap forces.
6. There is a decoy in the tree with exactly the right name. `expected_artifacts`
   / `artifacts_present` (`factory/verify/models.py:563` — `OutputCheck`) look
   like this feature and are not: the docstring above them
   (`factory/verify/models.py:527` — `OutputCheck`) is explicit that they are the
   anti-rubber-stamp check for read-scope nodes, and the one production caller
   passes an empty list literally inside `_verify`
   (`factory/workgraph/workflow.py:2714` — `_verify`).
7. And the place the bytes would have to land is a question the workflow cannot
   answer. `_verify` (`factory/workgraph/workflow.py:2700` — `_verify`) builds
   `RunGatesInput` (`factory/activities/verify_activities.py:217` —
   `RunGatesInput`) with one argument, and workflow code may read neither the
   environment nor the filesystem; `EpicInput` (`factory/workgraph/workflow.py:578`
   — `EpicInput`) carries a graph, a proxy url, dials and no runtime root. The
   host location is an activity-side fact everywhere else in this repository —
   `_store_path` (`factory/activities/verify_activities.py:634` — `_store_path`)
   and `factory_root` (`factory/activities/agent_activities.py:179` —
   `factory_root`) both resolve it inside an activity — and it must be one here.

## The rule this spec is asking for

**A gate declares the artifact it writes and the type it writes it in; the
platform collects it at the boundary into the per-attempt record, storing the
bytes in one absolute place the activity resolves; and an exported reader returns
it per attempt.**

Four types the platform understands — `sbom`, `coverage`, `scan`, `opaque` —
because a consumer that must sniff the format has per-repo fragmentation back, and
because an unrecognised artifact must still be carried and still be attributable.

Declaring an artifact must not change a gate's verdict in either direction, and
that is where the inputs combine. The worktree watch (084) demotes a gate that
succeeded and changed the tree the judge's patch is assembled from, unless the
manifest named that gate a legitimate writer; the watch is blind to git-ignored
paths by construction. Every row below is what this spec must produce:

| What the gate wrote | Declared as an artifact | `writes:` for that gate | Watch sees the path | Gate status | Record |
| --- | --- | --- | --- | --- | --- |
| nothing | yes | false | — | `PASS`, as today | the artifact, declared and absent |
| the artifact, at an unignored path | yes | false | yes | `PASS` (FR-004) | the artifact, collected |
| the artifact, at a git-ignored path | yes | false | no | `PASS`, as today | the artifact, collected |
| the artifact **and** some other path | yes, the artifact only | false | both | `DIRTIED_WORKTREE` (FR-005) | the artifact, collected |
| some other path | no | false | yes | `DIRTIED_WORKTREE` (FR-005) | no artifact |
| some other path | no | true | yes | `PASS`, as today (084 FR-010) | no artifact |
| anything, snapshot unreadable | yes | false | error | `DIRTIED_WORKTREE`, as today | the artifact, collected |

Row four is the whole reason the exemption is per path and never per gate: a gate
that emits a declared artifact has signed for that path and for nothing else, and
an implementation that excuses the gate instead of the path silently retires 084's
watch for every artifact-emitting gate in the fleet.

The last row is the fail-closed rule `_to_result` already states in its own
docstring and this spec does not touch: declaring what a gate writes is not a
claim about a tree git refused. Collection is unaffected by it, because collection
reads the declared path from disk and never from the watch.

### What this spec is not

It is not a change to what the judge sees. Admitting a non-text artifact into the
judge's prompt is a separate question gated on a constitutional decision, and this
spec deliberately stops short of it.

It is not interpretation. The platform carries bytes and a declared type. It does
not parse coverage, resolve an SBOM, or grade a scan.

It is not a change to `writes:`. That key stays a per-gate boolean meaning "this
gate writes on purpose"; an artifact declaration is narrower and names one path.

It is not a new way to resolve the runtime root. The destination is resolved
inside the gate-running activity, which is where `_store_path`
(`factory/activities/verify_activities.py:634` — `_store_path`) and `factory_root`
(`factory/activities/agent_activities.py:179` — `factory_root`) already resolve
their own host locations; and it is resolved through the one engine resolver, the
way `factory_root` does and `_store_path` does not (plan.md § What already exists).
The workflow composes no filesystem path at all. Nothing here invents a fifth
resolver, so spec 129's work carries this spec along instead of colliding with it
— FR-017 asks only for the absolute path 129 makes unconditional.

It is not a claim about where that root sits, either. The runtime root is
git-ignored (`.gitignore:17-18`) and on the deployment that will build this spec
it is `/home/admin/code/ergane/.factory` — inside the target clone, which is
where the node worktrees already live. What this spec asserts is that the
destination comes from the resolver and lands outside the node worktree, never
that it lands outside the clone.

It is not a change for a repository that declares nothing. A manifest without the
new key behaves exactly as today.

## User Scenarios & Testing

### User Story 1 - A manifest declares the artifacts its gates write (Priority: P1)

As an operator, I can tell ergane which files my gates produce and what they are.

**Why this priority**: P1 and it depends on nothing. There is nothing to collect
until there is a declaration, and the declaration's shape is the part that is hard
to change later.

**Independent Test**: Load a manifest declaring artifacts and read the parsed
configuration; load malformed ones and read the refusals; render the parsed
configuration through the parser's own CLI and read the JSON.

**Acceptance Scenarios**:

1. **Given** a v2 manifest declaring a top-level `artifacts:` list beside
   `gates:`, each entry naming a declared gate, a repo-relative path and one of
   `sbom`, `coverage`, `scan`, `opaque`, **When** the manifest is loaded, **Then**
   it parses and the parsed configuration carries the entries in declaration
   order.
2. **Given** an entry naming a type outside that set, **When** the manifest is
   loaded, **Then** it is refused with a message naming the entry and the
   permitted types.
3. **Given** an entry naming a gate the manifest does not declare, **When** the
   manifest is loaded, **Then** it is refused with a message naming the entry and
   the declared gates.
4. **Given** an entry whose path is absolute, or is relative and escapes the
   repository root, **When** the manifest is loaded, **Then** it is refused with a
   message naming the path.
5. **Given** a manifest that declares no artifacts, **When** it is loaded, **Then**
   the parsed configuration is equal, in every field that existed before this
   story, to what that same manifest parsed to before it, and its artifact field
   is empty — the control is written that way because a defaulted new field makes
   whole-object equality impossible to satisfy honestly.
6. **Given** a v1 manifest declaring `artifacts:`, **When** it is loaded, **Then**
   it is refused as an unknown top-level key on the same path every other v2-only
   key is refused.
7. **Given** a parsed configuration carrying artifact declarations, **When** the
   manifest parser's own CLI renders it, **Then** stdout is one JSON document
   whose artifact entries carry the declared path and type as strings, because
   that document is the only way the declaration reaches the gate runner.
8. **Given** an entry whose path stays inside the repository but is spelled with a
   redundant `./` prefix, and another spelled with an interior `..` segment that
   resolves back inside it, **When** the manifest is loaded, **Then** both parse
   and each carried path is the normalised worktree-root-relative spelling — the
   one `git diff-tree --name-only` itself prints — because the only consumer that
   compares this path compares it to git's output by string equality, and a path
   carried as declared would collect correctly and still demote its own gate.

### User Story 2 - A declared artifact reaches the runner and the gate's write exemption (Priority: P2)

As an operator, declaring an artifact does not make my gate fail for writing it.

**Why this priority**: P2 and it depends on US1. This story exists because without
it the feature is self-defeating: a declared artifact path is *by definition* a
gate write, and the existing worktree watch demotes a gate that wrote when nobody
signed for it. Shipping US3 without this demotes every artifact-emitting gate
whose artifact is not git-ignored.

**Independent Test**: Declare an artifact, run a gate that writes it, and read the
gate's result; run a gate that writes its artifact and one undeclared path beside
it, and read the result; run the same declaration through the candidate-acceptance
route and read what the runner received.

**Acceptance Scenarios**:

1. **Given** a gate declaring an artifact at a path the repository does **not**
   git-ignore, **When** the gate exits 0 having written exactly that path,
   **Then** its status is `PASS` and the path is still listed in its
   `worktree_writes`, because the declaration moves the verdict and never the
   recording.
2. **Given** a gate that exits 0 having written a path declared neither as an
   artifact nor through `writes:`, **When** its result is composed, **Then** its
   status is `DIRTIED_WORKTREE` exactly as today.
3. **Given** a gate that declares an artifact and does not write it, **When** its
   result is composed, **Then** its status is whatever its exit code and deadline
   made it, unchanged, because a missing artifact is a collection fact and not a
   gate verdict.
4. **Given** a worktree whose own manifest parser accepts the manifest — the
   candidate-acceptance route every Ergane node takes — **When** the gate runner
   is handed that acceptance, **Then** the artifact declarations arrive on the
   runner, not only on the in-process fallback path.
5. **Given** a gate whose written paths were all declared artifacts but whose
   worktree snapshot git refused to read, **When** its result is composed,
   **Then** its status is `DIRTIED_WORKTREE` exactly as today, because a
   declaration is not a claim about a tree the check could not read.
6. **Given** a gate that exits 0 having written **both** the path it declared as
   an artifact and one unignored path it declared nowhere, **When** its result is
   composed, **Then** its status is `DIRTIED_WORKTREE` and both paths are listed
   in its `worktree_writes`, because the exemption subtracts the declared path and
   never excuses the gate.

### User Story 3 - The boundary collects what was declared (Priority: P2)

As an operator, the artifact my gate wrote is attached to the attempt that wrote
it.

**Why this priority**: P2 and it depends on US2. It is the story the whole spec is
for, and it is second only because collecting an artifact that demotes its own
gate would be worse than not collecting it.

**Independent Test**: Call the gate runner directly with a destination outside the
worktree and declarations naming a written file, an unwritten file, an oversized
file and a malformed file, then read the returned records and the destination
directory.

**Acceptance Scenarios**:

1. **Given** an attempt whose gate wrote a declared artifact, **When** the gate
   boundary composes its results, **Then** that gate's `GateResult.artifacts`
   carries one `GateArtifact` naming the declared path, the declared type, that it
   was present, its size in bytes, and the location its bytes were copied to, and
   that location holds the same bytes the gate wrote.
2. **Given** a declared artifact the gate did not write, **When** the boundary
   composes its results, **Then** the record carries a `GateArtifact` for it
   marked absent, rather than omitting it, because omission makes "the gate did
   not emit it" indistinguishable from "nobody declared it".
3. **Given** a declared artifact of type `opaque`, **When** it is collected,
   **Then** its record carries the same fields, filled the same way, as a
   `coverage` artifact's does.
4. **Given** a declared artifact larger than the platform's stored-bytes limit,
   **When** it is collected, **Then** its record says present, carries its true
   size, and names no stored location, and no truncated copy is written — a
   truncated SBOM is a corrupt SBOM.
5. **Given** an artifact of any size, **When** the boundary returns its results,
   **Then** the returned records carry a reference to the stored bytes and never
   the bytes, proven by a committed test asserting the serialised result stays
   within a fixed size while the artifact grows.
6. **Given** a declared `coverage` artifact whose bytes are not well-formed XML,
   **When** it is collected, **Then** it is collected and recorded exactly as a
   well-formed one is, because the platform carries bytes and a declared type and
   grades neither.
7. **Given** an attempt in a repository declaring no artifacts, **When** the
   boundary composes its results, **Then** every `GateResult.artifacts` is empty,
   nothing is copied anywhere, and each gate's result is equal, in every field
   that existed before this story, to the result that gate produced before it.
8. **Given** two gates where the first declares and writes an artifact that is
   collected, **When** the second gate runs after it, **Then** the second gate's
   status and `worktree_writes` are exactly what they are when nothing is
   declared, because the boundary hands each gate's closing snapshot to the next
   one as its opening snapshot and a byte written inside the watched worktree
   after that snapshot is charged to the wrong gate.
9. **Given** an attempt with collected artifacts, **When** the judge's prompt is
   assembled for it, **Then** the prompt is byte-identical to the prompt assembled
   for the same attempt with no artifacts declared.
10. **Given** a lexically accepted artifact path resolves through an escaping or swapped symlink, a hardlink alias or a special file, **When** the real collector opens it, **Then** committed tests prove bounded refusal without reading outside the permitted worktree, blocking on a FIFO or changing the gate verdict, and the artifact record names the refusal.
11. **Given** an artifact already exists before its gate and is unchanged, is newly written, or changes while being captured, **When** collection runs, **Then** committed tests prove capture provenance distinguishes those observations and refuses an inconsistent snapshot instead of certifying every present file as newly produced by that gate.

### User Story 5 - The bytes land in one absolute place the activity resolves (Priority: P2)

As an operator, an artifact my gate wrote outlives the worktree it was written in,
in a place I can name.

**Why this priority**: P2 and it depends on US3. US3 collects into a destination
it is handed; this story decides where that destination comes from and makes the
record survive the store. It is separate because it is the half that cannot be
decided inside the collector: the workflow may not resolve a path and the activity
must.

**Independent Test**: Run the gate-running activity with an attempt's identity and
a runtime root named by the environment, and read the destination it composed;
write and re-read an attempt's row, including a row written before this spec.

**Acceptance Scenarios**:

1. **Given** a gate-running activity request carrying the epic id, the node id and
   the attempt number, **When** the activity runs the gates, **Then** the
   destination it hands the runner is an absolute path under the runtime root the
   engine's own resolver returns, scoped to that epic, node and attempt, and
   outside the node worktree, proven by a committed test asserting the path the
   runner received and asserting that the same request under a different resolved
   root composes a different destination — the destination comes from the
   resolver's answer and from no other path on the request.
2. **Given** the workflow's verification step, **When** it builds the
   gate-running activity's input, **Then** the input it constructs carries the
   epic id, the node id and the attempt, sets no filesystem path but the worktree
   — `factory_yaml_path` left at its default — and composes nothing, because
   workflow code may read neither the environment nor the filesystem, proven by a
   committed test asserting the input the activity received.
3. **Given** an environment in which the engine's runtime-root resolver answers
   with a relative path, **When** the activity composes the destination, **Then**
   the destination it composes and the location it records are absolute, because a
   relative root resolves against whichever directory the worker happens to be in.
4. **Given** an attempt whose gate results carry collected artifacts, **When** the
   row is written and read back, **Then** each artifact returns with its declared
   path, its declared type, whether it was present, its size and its stored
   location.
5. **Given** a stored row written before this spec, whose gate results carry no
   artifact key at all, **When** it is read back, **Then** it decodes to a
   `GateResult` equal in every field that existed before this story, with the
   artifact field empty, and the schema is unchanged.
6. **Given** an attempt in a repository declaring no artifacts, **When** its row
   is written, **Then** the row decodes to a result equal, in every field that
   existed before this story, to what the same attempt stored before it.
7. **Given** two dispatches or two captures share an epic/node/attempt ordinal, **When** both store different bytes and one capture is redelivered, **Then** committed tests prove each retains its own immutable location and digest, identical redelivery is idempotent, and conflicting bytes cannot overwrite the earlier capture.

### User Story 4 - An exported reader returns them per attempt (Priority: P3)

As a consumer, I can read an attempt's artifacts without shelling a CLI.

**Why this priority**: P3 and it depends on US5. A reader must exist or nothing can
display it — that is PR-3's central argument — but it is worthless until there is
something stored to read.

**Independent Test**: Store two attempts of one node with different artifacts, then
call the exported reader for each.

**Acceptance Scenarios**:

1. **Given** an attempt whose stored row carries collected artifacts, **When** the
   exported reader is called for that epic, node and attempt over a read-only
   connection, **Then** it returns each artifact with its declared path, its
   declared type, the name of the gate that produced it, whether it was present,
   and where its bytes were stored.
2. **Given** two attempts of the same node whose artifacts differ, **When** the
   reader is called for each, **Then** each call returns its own attempt's set and
   neither returns the other's.
3. **Given** an attempt whose row carries no artifacts, **When** the reader is
   called, **Then** it returns an empty tuple rather than raising.
4. **Given** two dispatches share the requested node/attempt, **When** the reader is called with explicit dispatch and capture identity, **Then** a committed test proves it returns only that capture with digest/status/freshness provenance, and an ambiguous old-style request refuses rather than combining both as one attempt.

## Functional Requirements

- **FR-001**: The v2 manifest MUST accept a top-level `artifacts:` list beside
  `gates:`, each entry naming a gate, a path that gate writes, and a type from
  `sbom`, `coverage`, `scan`, `opaque`, and the parsed configuration MUST carry
  them in declaration order. The key is spelled `artifacts:` here rather than left
  to an implementer because it is the most public identifier this spec creates:
  every target repository's manifest carries it forever, and spec 128 is adding
  its own v2 sibling key (`boundary_only_gates`) to the same tuple.
- **FR-002**: An entry naming a type outside that set, or a gate the manifest does
  not declare, MUST be refused with the entry named.
- **FR-003**: A manifest declaring no artifacts MUST parse and behave exactly as
  today, and `artifacts:` MUST be refused on a v1 manifest as an unknown top-level
  key.
- **FR-004**: A gate that exits 0 having written a path it declared as an artifact
  MUST keep the status it would have had with no writes, while that path stays
  recorded in its `worktree_writes`.
- **FR-005**: A gate that writes a path declared neither as an artifact nor
  through `writes:` MUST still be demoted exactly as today, **including when that
  same gate also wrote a path it did declare** — the exemption subtracts the
  declared paths and never excuses the gate; a gate that declares an artifact
  without writing it MUST keep its own verdict unchanged; and an unreadable
  worktree snapshot MUST still demote, artifact declarations notwithstanding.
- **FR-006**: The gate boundary MUST collect each declared artifact into
  `GateResult.artifacts` — a tuple of `GateArtifact` records, each naming the
  declared path, the declared type, whether the artifact was present, its size in
  bytes, and the location its bytes were actually written to — attributed to the
  gate that declared it.
- **FR-007**: A declared artifact that was not written MUST be recorded present as
  false rather than omitted.
- **FR-008**: An `opaque` artifact MUST be carried and attributed exactly as a
  recognised type is.
- **FR-009**: The platform MUST NOT parse or interpret an artifact's contents; an
  artifact whose bytes do not match its declared type MUST be collected and
  recorded exactly as a well-formed one is.
- **FR-010**: An exported read-only reader MUST return an attempt's artifacts with
  path, type, producing gate, presence and stored location, MUST scope them to
  that attempt, and MUST return an empty tuple rather than raising when there are
  none.
- **FR-011**: The judge's prompt MUST be unchanged by this spec; no collected
  artifact may reach it.
- **FR-012**: A declared artifact path MUST be repo-relative and MUST be refused
  at load time when it is absolute or when it escapes the repository root; and an
  accepted path MUST be carried in one normalised spelling — worktree-root-relative,
  posix separators, no `.` or `..` segment — because the only thing that ever
  compares it is the per-path subtraction FR-004 asks for, which is a string
  equality against `git diff-tree --name-only` output (plan.md trap 3). A path
  accepted verbatim as `./coverage.xml` parses, collects correctly and still demotes
  the gate for writing the artifact it declared.
- **FR-013**: The parsed configuration MUST stay renderable as one JSON document
  by the manifest parser's own CLI, because that document is how a declaration
  reaches the gate runner.
- **FR-014**: The declaration MUST reach the gate runner on both routes — the
  candidate acceptance a worktree's own parser produces, and the in-process
  fallback — so a repository that carries its own parser collects what it
  declared.
- **FR-015**: The platform MUST bound the bytes it stores per artifact by one
  named constant; an artifact above that bound MUST be recorded present with its
  true size and no stored location, and MUST NOT be truncated.
- **FR-016**: The per-attempt record MUST carry a reference to the stored bytes
  rather than the bytes themselves, so the gate-running activity's returned
  payload does not grow with an artifact's size.
- **FR-017**: The destination for collected bytes MUST be resolved and composed
  inside the gate-running activity, through the runtime-root resolver the engine
  already has, and MUST be an absolute path under that root, scoped to the epic,
  the node and the attempt, and outside the node worktree. It MUST be composed
  from the root that resolver returns and from no other path on the request —
  never from the target repository's path and never from the prepared worktree's.
  It MUST NOT be required to fall outside the target clone: the resolved root is
  git-ignored and on the deployment that will build this spec it sits inside the
  clone, alongside the node worktrees themselves (plan.md trap 15). The workflow
  MUST supply that identity and no filesystem path other than the worktree,
  because workflow code may read neither the environment nor the filesystem.
- **FR-018**: Collecting an artifact MUST NOT change any gate's status or its
  recorded `worktree_writes`, the gate that runs next included; the collector MUST
  NOT write inside the worktree it is watching.
- **FR-019**: An attempt's collected artifacts MUST survive the per-attempt store
  and return with path, type, presence, size and stored location; a row written
  before this spec MUST decode to a result equal in every field that existed
  before it, with the artifact field empty, and no schema migration may be added.
- **FR-020**: The collector MUST enforce source containment on opened regular files, refuse unsafe symlink/hardlink aliases and special files without blocking, bound reads, and record refusals without changing a gate verdict; lexical manifest validation alone MUST NOT be treated as runtime safety.
- **FR-021**: New persisted captures MUST carry dispatch and immutable capture identity plus content digest/status, preserve distinct bytes across reused ordinals, and make identical redelivery idempotent. Existing artifact-free payloads MUST remain readable, with no invented historical identity.
- **FR-022**: Capture MUST preserve whether bytes were observed preexisting/unchanged, newly written or changed during collection; unstable bytes MUST NOT be published as a consistent snapshot, and mere presence MUST NOT be claimed as proof the gate produced a fresh report.
- **FR-023**: The read-only reader MUST accept explicit dispatch/capture identity and return its digest, capture status and freshness provenance; ambiguous legacy selection MUST be refused rather than conflating distinct captures.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-012, FR-013]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-004, FR-005, FR-014]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-006, FR-007, FR-008, FR-009, FR-011, FR-015, FR-016, FR-018, FR-020, FR-022]
US5:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-017, FR-019, FR-021]
US4:
  depends_on: []
  depends_on_merged: [US5]
  implements: [FR-010, FR-023]
```

A chain, and each edge is declared rather than left inferred (069-US2 FR-007).
US2 reads the declaration US1 parses and threads it to the runner; US3 would
demote every artifact-emitting gate whose artifact is not git-ignored if it landed
before US2, and it collects through the runner parameter US2 adds; US5 supplies
the destination US3 collects into and stores what US3 records, so it is worthless
before US3 and US3 is inert without it; US4 reads what US5 stores.

The file map after the split is the reason the split is worth an extra node. US3
shares `factory/verify/models.py` with US1 and `factory/verify/gates.py` with US2;
US5 shares `factory/verify/store.py` with US4 and shares no file with US3 at all.
No two stories in this graph touch one file without an edge between them, and the
edges are all merge edges, so contention inference has nothing left to infer.

The ordering is also the risk ordering: the manifest shape is the hardest thing to
change after the fact, the self-defeating interaction with the worktree watch is
the one that would make a green US3 useless in practice, and the destination's
origin is the one design decision that cannot be deferred to an implementer,
because the component that would have to decide it is forbidden to.
