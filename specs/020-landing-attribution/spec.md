---
state: draft
# Drafted 2026-08-09 from an operator finding of 2026-08-08: the landed-facts
# reader points at the wrong history in two independent ways, and the two were
# folded into one decision because fixing either alone leaves the reader wrong.
#
# The finding surfaced while trying to dispatch 006's remainder.
# `factory-epic landed specs/006-interpreter-hardening` returned nothing for a
# spec with three stories in the tree, and `derive --delta` would have emitted
# all five — re-implementing three landed stories at attempt price. The
# remainder was dispatched from a hand-pruned graph instead, which is the
# workaround this spec exists to retire.
#
# Numbered 020: 010–014 stay reserved for audit-triage epics, 015 is the
# doctor, 016 the delta, 017 the peer channel, 018 agent home isolation, 019
# the operator CLI.
#
# Sequencing: this should land BEFORE 019-operator-cli. 019 renames these
# commands behind an `ergane` front door and touches the same parsers, so
# landing 020 second means re-verifying 019's reuse inventory against a moved
# target for no gain.
depends_on_landed: [016-delta-derivation]
---

# Feature Specification: Landing Attribution

**Feature Branch**: `020-landing-attribution`

**Created**: 2026-08-09

**Status**: Drafted after the workaround was used in anger. 006's remainder was
dispatched on 2026-08-09 from a hand-written `workgraph-remainder.json` because
the reader could not tell the operator which of its five stories were already in
the tree. That file is the third such hand-pruned graph (007 and 009 have their
own), and each one is a graph nobody validated against the spec it came from.

**Input**: Two defects, one symptom.

**The branch.** Three places in the tree answer "which branch does the factory
land on", and they give three different answers. `_build_baseline`
(`factory/workgraph/cli.py:348`) assigns the literal `"main"` and `derive`
exposes no flag to change it. `factory-epic landed` takes `--default-branch` but
defaults it to `"main"` (`factory/workgraph/cli.py:895`). The runtime asks the
clone what it has checked out (`_default_branch`,
`factory/workgraph/worktree.py:417`, `git symbolic-ref --short HEAD`). None of
the three reads a declaration, because there is nothing to read.

The runtime answer is the one that happens to be right today, and it is right by
operator convention rather than by construction: every live target clone happens
to sit on `ergane-buildout`. `ergane-003-target` does not — it sits on
`claude/install-matt-pocolk-skills-zl0cga`, which is how this surfaced — and
`_default_branch` feeds `capture_base_ref` (`factory/workgraph/worktree.py:176`),
so the checked-out branch of a clone decides what every node of an epic
**branches from**. This is not a reporting bug with a reporting fix. Worth
noting alongside: the GitHub repository's own default branch is already
`ergane-buildout`, so `"main"` is not merely a stale default — it is a literal
that was never revisited after the buildout branch became where work lands.

**The grammar.** `landed_facts` recognizes exactly one landing subject:
`<epic_id>/<node_id>: <STORY_KEY> (#<pr>)` (`_LANDING_RE`,
`factory/workgraph/landed.py:39`), which the merge queue renders through
`pr_title` (`factory/mergequeue/messages.py`, D-034). Everything the factory
landed *before* the queue existed used a different subject, written by git:
`Merge branch 'factory/<epic_id>/<node_id>' into <branch>`. Three such commits
are reachable from `ergane-buildout` today, all 006's. They are invisible to the
reader, so a spec with three landed stories reports zero, and the delta derived
from that report proposes to build all five.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The landing branch is declared once (Priority: P1)

As the factory operator, the branch the factory lands on is declared in the
target repository's manifest, so that every command and every dispatch reads one
answer instead of three, and a clone left on some other branch cannot silently
change what an epic builds from.

`factory.yaml` gains an optional top-level `landing_branch:`, beside `standards:`
and `gates:`. It defaults to `"main"` when absent, so every target repository
that does not declare one keeps working exactly as it does today. Ergane's own
manifest declares `ergane-buildout`.

This is D-009's rule — declared, never auto-detected — applied to the one fact
about a target repository the factory currently guesses at three times.

An explicit `--default-branch` on the command line still wins: declaration
replaces the *default*, not the operator's ability to ask a different question.

**Why this priority**: `capture_base_ref` is downstream of the same helper, so
this is what an epic branches from, not only what a report says.

**Independent Test**: With a manifest declaring a landing branch and a clone
checked out on an unrelated branch, the base an epic pins and the branch every
reader scans are both the declared one.

**Acceptance Scenarios**:

1. **Given** a target repository whose manifest declares
   `landing_branch: ergane-buildout`, **When** `factory-epic landed` runs with no
   flag, **Then** it scans `ergane-buildout`.
2. **Given** the same repository, **When** a delta derivation runs, **Then** its
   baseline is read from the declared branch rather than from `main`.
3. **Given** a clone checked out on an unrelated branch, **When** a node's base
   ref is captured, **Then** it is `origin/<declared>` — the checked-out branch
   does not decide what the epic builds from.
4. **Given** a target repository whose manifest declares no landing branch,
   **When** any of the above runs, **Then** behaviour is exactly what it is
   today, and no existing target repository is required to change.
5. **Given** an explicit `--default-branch` on the command line, **When** it
   disagrees with the manifest, **Then** the flag wins and the manifest is not
   consulted.
6. **Given** a manifest declaring `landing_branch:` with no value, or a
   non-string, **When** it is loaded, **Then** the load fails naming the key —
   the same discipline `standards` already applies, where declared means
   declared.

---

### User Story 2 - Landings older than the merge queue are read as history (Priority: P1)

As the factory operator, a story landed before the merge queue existed is
reported as landed, so that a delta derivation proposes the work that remains
rather than the work already in the tree.

A second recognizer for `Merge branch 'factory/<epic_id>/<node_id>' into
<branch>`, scanned in the same pass as the queue grammar. `git log` already
includes merge commits — `_git_log_subjects`
(`factory/workgraph/landed.py:154`) passes no `--no-merges` — so only the
recognizer changes and no new git call is added.

The story key is inferred from the node id by upper-casing, which is sound for
exactly one reason and the plan must cite it: the deriver mints node ids as
`story_key.lower()` (`factory/workgraph/derive.py:184`). That is the whole
justification, and an inference without it is a guess.

The provenance stays honest. `LandedKind` (`factory/workgraph/landed.py:47`)
carries `OBSERVED` and `ATTESTED` today; the historical form is neither, and
collapsing it into `OBSERVED` would tell a reader that a fact came from the
attribution contract when it came from a subject git wrote.

**Why this priority**: it is the half that unblocks the delta, and the delta is
what makes a partly-landed spec dispatchable without a hand-written graph.

**Independent Test**: Against a repository holding 006's three pre-queue merges,
`factory-epic landed` reports US1, US2 and US5 with the historical kind, and a
delta derivation emits only the stories that are genuinely absent.

**Acceptance Scenarios**:

1. **Given** a commit subject `Merge branch 'factory/<epic>/<node>' into
   <branch>` reachable from the scanned branch, **When** landed facts are read
   for that epic, **Then** the story is reported landed at that commit.
2. **Given** such a fact, **When** its kind is inspected, **Then** it is
   distinguishable from both `OBSERVED` and `ATTESTED`, and the human rendering
   says which.
3. **Given** a story with both a pre-queue merge and a later queue landing,
   **When** facts are read, **Then** the queue landing wins, because it is newer
   — the scan is newest-first and first-seen-wins, and this must be stated as a
   rule rather than left as a property of the loop's shape.
4. **Given** subjects that must not match — `salvage(<epic>/<node>): completed
   attempt 1`, which is in every branch's history, and an operator commit like
   `<epic>: US4 — <prose>`, which names a story but no node — **When** the scan
   runs, **Then** neither is read as a landing.
5. **Given** a merge commit for a different epic, **When** facts are read for
   this epic, **Then** it is ignored, exactly as the queue grammar already
   ignores it.
6. **Given** 006's three pre-queue merges and its two unlanded stories, **When**
   a delta derivation runs against the declared branch, **Then** it emits US3 and
   US4 and nothing else — or nothing at all, if those have landed by then.

---

### Edge Cases

- A pre-queue merge whose node id does not upper-case to a story key the spec
  declares is not a landing for a story that does not exist. Ignore it rather
  than inventing a story key; the spec's own requirements are the authority on
  what stories there are.
- A repository with no `factory.yaml` at all, or one the schema refuses, already
  reads as "declares no standards" rather than failing (`_read_standards`,
  `factory/verify/factory_yaml.py:268`). The landing branch takes the same
  posture for absence — absent means `"main"` — but **not** for a malformed
  declaration, which fails like any other malformed key.
- The three hand-pruned remainder graphs already in the tree
  (`specs/007-parallel-dispatch/workgraph-remainder.json`,
  `specs/009-roadmap-scheduler/workgraph-remainder.json`,
  `specs/006-interpreter-hardening/workgraph-remainder.json`) are not inputs to
  anything and are not migrated. They are the workaround this spec retires, and
  they stay as the record of it.
- `_build_baseline` reads the target repo from the spec's sibling directory
  rather than from `--target-repo` (`factory/workgraph/cli.py:346`, and its
  docstring says so). That is a separate oddity and is **out of scope**; this
  spec changes which branch is read, not which repository.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `factory.yaml` MUST accept an optional top-level `landing_branch`
  naming the branch the factory lands on. Absent MUST mean `"main"`, so no
  existing target repository is required to change. Declared-but-empty or
  non-string MUST fail the load naming the key, in the same shape as `standards`.
- **FR-002**: Every reader of landed facts MUST take its default branch from the
  manifest: `factory-epic landed`'s flag default and the delta baseline
  (`_build_baseline`), which today has no flag at all. An explicit
  `--default-branch` MUST still override.
- **FR-003**: The base ref an epic's nodes are pinned to MUST come from the
  declared branch when one is declared, so that a target clone checked out on an
  unrelated branch cannot change what an epic builds from. Absent a declaration,
  today's behaviour — the clone's checked-out branch — MUST be preserved.
- **FR-004**: The roadmap's own branch resolution MUST read the manifest, falling
  back to its current behaviour only when nothing is declared.
- **FR-005**: `landed_facts` MUST recognize `Merge branch
  'factory/<epic_id>/<node_id>' into <branch>` as a landing for `<epic_id>`,
  deriving the story key from the node id, in the same single `git log` pass.
- **FR-006**: A fact from the historical grammar MUST carry a `LandedKind`
  distinct from `OBSERVED` and `ATTESTED`, and the human rendering MUST show it.
- **FR-007**: When one story has landings under both grammars, the newest MUST
  win. The rule MUST be asserted by a test rather than inherited from the scan
  order.
- **FR-008**: Subjects that name an epic and node without being landings — the
  salvage subject foremost — MUST NOT match either recognizer.

### Key Entities

- **Landing branch** — the branch the factory lands on, declared once in the
  target repository's manifest; the answer to a question three call sites
  currently guess at.
- **Historical landing** — a landing recorded by a merge commit git wrote,
  before the merge queue owned the subject line. A landing, with its own
  provenance kind.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `factory-epic landed specs/006-interpreter-hardening` with no flag
  reports US1, US2 and US5, each marked with the historical kind.
- **SC-002**: `factory-epic derive specs/006-interpreter-hardening --delta`
  emits only stories genuinely absent from the declared branch — never a story
  whose merge commit is reachable.
- **SC-003**: A target clone checked out on an unrelated branch pins
  `origin/<declared>` as its base ref, proved by a test rather than by
  convention.
- **SC-004**: A target repository declaring nothing behaves exactly as it does
  today, across every path this spec touches.
- **SC-005**: The full suite stays green and no dependency is added.
- **SC-006**: No future spec needs a hand-written `workgraph-remainder.json` to
  dispatch a partly-landed spec.

## Work Graph

Two stories, and they are genuinely independent: US1 is the manifest key and the
call sites that read a branch, US2 is a regex and a enum member in
`factory/workgraph/landed.py`. They share no file — `landed.py` reads the branch
it is *given* and does not choose it.

They are nonetheless sequenced on a merge edge rather than dispatched as a pair,
because the acceptance evidence for US2 is `factory-epic landed` returning 006's
three landings **with no flag**, and that is US1's behaviour. Dispatched as
siblings, US2's verification would have to pass a flag that US1 is in the middle
of making unnecessary, and the judge would be scoring a workaround.

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-005, FR-006, FR-007, FR-008]
```

## Assumptions

- **The historical grammar is closed, not growing.** Exactly three commits use
  it, all 006's, and the merge queue has owned every landing since. This is a
  reader that must understand history, not a second contract the factory will go
  on writing. FR-005 adds no writer.
- **`git log` already sees merge commits.** Verified: `_git_log_subjects`
  (`factory/workgraph/landed.py:154`) passes no `--no-merges`. If that ever
  changes, US2 breaks silently — which is a reason for its tests to run against
  a fixture repository containing a real merge commit rather than against a
  list of subject strings.
- **Upper-casing a node id is sound only because the deriver lower-cases the
  story key.** `factory/workgraph/derive.py:184`. If node ids ever stop being
  derived that way, the inference stops being valid, and the test that catches
  it is the round-trip: derive a graph, and assert every node id upper-cases to
  its own `story_key`.
- **006 is the acceptance case, and it may be a moving one.** Its remainder was
  dispatched on 2026-08-09. If US3 and US4 land before this spec does, SC-002's
  expected output becomes "nothing" rather than "US3 and US4" — which is still a
  pass, and the test should be written against a fixture repository so it does
  not depend on which day it runs.
- **No new dependency, no store, no workflow change.** One optional manifest
  key, one regex, one enum member, and the call sites that read a branch.
- **`main` is not being retired.** It remains the default for every target
  repository that declares nothing, and remains where Ergane's operator promotes
  to. This spec changes what the factory *reads*, not where anything lands.
