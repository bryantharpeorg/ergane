---
state: draft
depends_on_landed:
  - 133-spec-validate-has-one-implementation-and-two-faces
fixes:
  - feedback/pr-7-a-write-seam-for-the-spec-state-transitions-the-operator-actually-performs
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04-tail) from
# docs/triage-2026-09-03-ergane-web-round3.md § "declaring-a-spec-ready-is-a-verb-that-can-refuse"
# (lines 364-380), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit with sed and verified to resolve
# to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. PR-7 of the `ergane-web` consolidated hand-over, filed
# 2026-08-29 by a consumer repository that is itself a target of this factory.
# The most expensive act in the product — the flip that causes the roadmap to
# dispatch nodes that spend tokens, open pull requests and move the landing
# branch — is two characters edited into a markdown file, with nothing that
# validates it, records it or can refuse it. The ask was restated by its own
# author: the original was CLI-shaped and that is the one thing it got wrong.
# The deliverable is typed functions in `factory.*`; the verb is how a human
# reaches them.
#
# WHAT IT COST, MEASURED. The ledger row records one story lost: on 2026-08-25
# an operator flip was lost because the pull request carrying it was armed for
# auto-merge before the edit was written, so the branch merged its pre-flip tree,
# the spec landed reading `draft`, and a second pull request was needed. The
# standing exposure is the interval, not the incident: `cadence_s` defaults to
# 300 seconds, so an unreviewed edit becomes a dispatched epic inside one tick,
# and on this floor the roadmap reads the operator's own working tree.
#
# THE TWO PRECONDITIONS ARE NOT SYMMETRIC TODAY, AND THAT IS WHY THIS BLOCKS ON
# 133. `ready`'s first precondition is "validate clean", and at 602a92c that
# verdict exists only as an exit code printed by a function that takes an
# `argparse.Namespace`. The second — "every `depends_on_landed` edge satisfiable"
# — is already a value, `compute_readiness`, but it is read three different ways
# in this tree and a fourth reading is exactly how this verb comes to permit a
# flip the roadmap then refuses. 133 makes the first half a value; this spec
# refuses to add the fourth reading of the second.
#
# THE ENTRY'S N50 HOLD DOES NOT BIND THIS REPOSITORY, AND ITS "SHARED WITH THE
# ROADMAP" CLAIM WAS WRONG. The source entry holds this work behind N50 because
# "the smallest useful slice writes frontmatter into the onboarded checkout". It
# does not here: `read_corpus_activity` reads the corpus off the worker host's
# own specs root every tick, not out of the target clone, so the file this verb
# writes is the file the next tick parses. That hold survives only for a consumer
# whose specs live inside the onboarded checkout. The same entry calls the two
# preconditions "the preconditions the roadmap already computes"; the roadmap
# computes only the edges — its pre-dispatch surface is clone, derive, preflight
# and onboarding, and none of it runs `spec validate`. "Validate clean" is a
# precondition this verb introduces, taken from 133's library form, which is why
# 133 is a hard edge and not a convenience.
#
# THE ONE KEY IS DECLARED WHOLE. `feedback/pr-7-a-write-seam-for-the-spec-state-transitions-the-operator-actually-performs`
# is open in the ledger and its summary asks for exactly this: "spec ready / spec
# defer as typed library functions with a plan/apply pair, refusing an illegal
# transition and naming the unmet edge". Every clause maps onto a requirement
# below — the pair onto FR-001 through FR-007, the illegal transition onto
# FR-004, the unmet edge onto FR-010 — so no half of it is left for a later spec
# to finish. Its two filed `refs` have rotted since 2026-08-29:
# `factory/cli/nouns/spec.py:90` now lands inside an unrelated registry helper,
# while `factory/roadmap/models.py:66` still resolves. Nothing else is declared,
# and no key was removed.
#
# NOT IN SCOPE. This spec does not add an attestation verb — `spec attest` came
# off this docket by the consumer's own narrowing, and `state: landed` stays what
# `SpecState`'s docstring calls it. It does not change `SpecState`'s meaning, its
# members, or the closed frontmatter key set. It does not touch the roadmap's
# `promote_spec` signal, `_apply_promotions`, or any workflow file. It does not
# make `spec new`, `spec derive`, `spec list` or `spec landed` behave differently,
# and it writes no provenance comment of its own into anyone's frontmatter.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail), against ergane-buildout at
# 602a92c, after an adversarial review refuted the draft on two blocking defects:
# (1) THE PRECONDITION WAS HOLLOW BY DEFAULT. FR-013 told the verb to copy
# `validate`'s `--target-repo` default, the literal `/srv/factory/targets/short-links`,
# which does not exist on this host — `ergane spec validate <dir> --specs-root specs`
# run that way skips `anchor_resolution`, `symbol_anchors` and `evidence`, prints
# "all pass" and exits 0. The verb would have declared the precondition met on a
# nine-of-twelve verdict. FR-013 now defaults the flag to the repository holding
# the specs root, and new FR-017 refuses at layer `validate_skipped` on any
# skipped layer: skipped is not clean. US2-S6, US3-S6 and trap 14 carry it.
# (2) THE REFUSAL CARDINALITY CONTRADICTED ITSELF: FR-009 said one refusal per
# refusing *layer* while tasks.md asserted one per refusal, and a layer emits one
# finding per bad anchor. FR-009, US2-S2, trap 10 and T016 now all say one
# `StateRefusal` per refusal in the report.
# Also repaired, from the minor findings: a corpus that does not parse made the
# planner raise rather than refuse, so FR-018, a `corpus` table row, US2-S7 and
# trap 15 were added; the gap's first sentence said "not one of them writes" when
# `spec new` writes a whole trio (it writes no *declared state*, which is the
# claim); "the only occurrence of the word" is now "the only `"ready"` literal",
# the count that is actually true; the tree emits `state:` lines in TWO scaffold
# functions, not one, both fresh drafts; trap 3's untracked-spec count was eight
# and is now twenty-seven, `127` through `153`; trap 1 gained the second lossy
# route (`_split_frontmatter` returns joined lines, so rebuilding the file from
# its two return values drops the trailing newline); T014's "no git invocation"
# became three named assertions; T025's ":216 is fine" now names the block it
# follows. Two holds are restated rather than lost: the source entry's trap 5 —
# 090 (c3a2e44/5c98cbf/ab165da) is NOT an ancestor of v0.5.0, so this lands for
# this floor immediately and reaches a consumer only after the next release cut —
# and the ledger row's own note that PR-7 was "merged with PR-8", whose half is
# delivered by the `depends_on_landed` edge 133, which declares
# `feedback/pr-8-spec-validate-has-no-library-form-and-its-composition-is-the-policy`;
# the key closes whole when this spec lands on top of that one. State stays draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail): a second adversarial review
# refuted the repaired draft on two blocking defects, both re-derived against the
# tree at 602a92c before this pass changed a line, and on four minor ones.
# (1) A TASK ASSERTED WHAT THE TREE HAD ALREADY FALSIFIED. The identity test told
# the implementer to assert that `factory/roadmap/models.py` carries "no import
# from `factory.workgraph`" — but `factory/roadmap/models.py:53` reads
# `from factory.workgraph.models import find_cycle`, and
# `factory/roadmap/models.py:374` — `_cross_validate` calls it at
# `factory/roadmap/models.py:400`, which is the corpus cycle check `read_roadmap`
# runs at `factory/roadmap/models.py:475`. Written as instructed the assertion is
# red on arrival and stays red after the story is correct, and the cheap way to
# green it deletes a load-bearing import three other specs depend on. The
# assertion now names the two git-reading modules — `factory.workgraph.landed`
# and `factory.workgraph.worktree` — and names `find_cycle` as the survivor that
# must not be removed. FR-011, US2-S2, trap 4 and T010 carry it.
# (2) THE RELOCATION AND THE PRECONDITIONS WERE TWO PULL REQUESTS IN ONE NODE.
# Measured on this tree: the six symbols the move relocates are 4,768 bytes over
# 133 lines (`factory/cli/status.py:247-251` and
# `factory/cli/status.py:378-505`), and they appear twice in a diff. Beside them
# the old US2 carried four precondition layers, seven tests and a pasted
# transcript — 900 to 1,000 changed lines at the 58 to 62 bytes per changed line
# this repository's own recent commits measure (602a92c: 906 lines, 52,840 B;
# 1027a05: 1,025 lines, 63,932 B), which lands within ten percent of
# `factory/verify/diffbounds.py`'s `DIFF_INPUT_LIMIT`, above which a story is
# refused unjudged before the judge is reached (D-050). US2 is now the relocation
# alone; a new US4 carries the preconditions. No existing story number moved, the
# chain US1 -> US2 -> US4 -> US3 is declared rather than inferred, and § Sizing
# now states each story's measured byte estimate and the point at which an
# implementer must stop and escalate rather than ship. The scenario ids the
# entry above names are the pre-split numbering and are not re-declared: the old
# US2-S5 is now US2-S1, and the old US2-S1, S2, S3, S4, S6 and S7 are US4-S1
# through US4-S6 in that order.
# Also repaired, from the minor findings: FR-009 and FR-017 now pin what a
# two-field `StateRefusal` does with the report's own layer name — the refusal's
# layer is `validate` or `validate_skipped` and its message is
# `<layer>: <message>` — which FR-001's two fields had left an implementer to
# invent twice, differently, and then assert its own invention; FR-011 and its
# task now name the two module-level imports the moved functions read,
# `landing_branch` at `factory/cli/status.py:110` and `_landing_head` at
# `factory/cli/status.py:106` (an alias of
# `factory.workgraph.landed._resolve_default_head`), which a mover of exactly the
# six named symbols would strand; plan.md's header now says which of its
# citations into `factory/cli/nouns/spec.py` are coordinates in the pre-133 tree
# rather than edit sites; plan.md § Sizing names 131, 140 and 153 as sibling
# drafts anchoring the symbols US2 relocates, and says which of the four must be
# flipped first; and trap 14's pasted transcript now carries the two
# `noted, not a refusal` lines the real run prints between the skips and the
# all-pass line. `fixes:` is unchanged, and state stays draft.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail, cross-batch): a completeness
# critic held the second review's US2 defect open, and it was re-derived against
# 602a92c before this pass changed a line. US2-S2 was satisfied in full by the
# tree as it stands, with zero production change: `factory/roadmap/models.py`
# imports only `from factory.workgraph.models import find_cycle` (line 53), a
# search of that file for `subprocess`, `factory.workgraph.landed`,
# `factory.workgraph.worktree` and a `["git", ...]` literal returns nothing, and
# `factory/roadmap/models.py:570` — `compute_readiness` already takes
# `landed_for` and `drifted_for`. US2 does not edit that file at all — its move
# is out of `factory/cli/status.py` — so the scenario's Given named a file the
# story never touches, and a test-only diff proved its Then. The procedural half
# compounded it: the task carrying that assertion sat under "Tests for this
# story (write FIRST, must fail)" while being green on arrival and green after
# the story was correct, and said nothing about it, so the implementer's cheapest
# route to a red test was to widen the assertion back to "no import from
# `factory.workgraph`" — the exact instruction the previous review removed.
# US2-S2's Then is now a fact only the move makes true: one definition site for
# the six names, under `factory/spec/`, which both readers take the readiness
# answer from — the status module's own body defines none of them, and the two
# resolvers report a `factory.spec` `__module__`. The negative survives as the
# scenario's second clause, and its task moved out of the red-first phase into a
# new "### Non-regression control for this story" sub-section, labelled the way
# trap 13's red is labelled but inverted: green on arrival, green after the story
# is correct, and that is what it is for. Task ids from the old T012 on shifted
# by one to make room — T011 is now the red, T012 the control; the pasted gate
# transcript in plan.md trap 14 was re-stated for the shifted ids, and trap 4 now
# says which half of it is the red and which the control. No FR, no story number
# and no `fixes:` key changed, and state stays draft.
---

# Feature Specification: declaring a spec ready is a verb that can refuse

**Created**: 2026-09-04
**Depends on**: `133-spec-validate-has-one-implementation-and-two-faces`, which
turns the validation verdict into a value a program can hold. `ready`'s first
precondition *is* that verdict, and a verb that cannot reach it cannot refuse
honestly.

## The gap, stated precisely

1. The `spec` noun registers five verbs and not one of them writes a spec's
   declared state. `factory/cli/nouns/spec.py:113` — `_add_spec_parser` adds
   `list` at `factory/cli/nouns/spec.py:117`, `validate` at
   `factory/cli/nouns/spec.py:134`, `derive` at `factory/cli/nouns/spec.py:156`,
   `new` at `factory/cli/nouns/spec.py:189` and `landed` at
   `factory/cli/nouns/spec.py:216`. `new` writes a whole trio; none of the five
   edits a `state:` line. There is no frontmatter state writer anywhere under
   `factory/`: the only `"ready"` literal in that module is
   `_DISPATCHABLE_STATES` at `factory/cli/nouns/spec.py:800`, and the only two
   places a `state:` line is emitted at all are the scaffold's fresh blocks —
   `factory/doctor/scaffold.py:158` — `_build_spec_md_from_slots` and
   `factory/doctor/scaffold.py:326` — `_build_spec_md`, the `findings promote`
   path — each of which writes `draft` into a file it is creating. Nothing edits
   an existing one.
2. That one line is the whole of what decides whether an epic is dispatched.
   `factory/roadmap/models.py:411` — `read_roadmap` parses each `spec.md`'s
   leading block into an entry, and `factory/roadmap/models.py:607` —
   `compute_readiness` computes `dispatchable = entry.state is SpecState.READY
   and not blockers`.
3. The roadmap filters its corpus on exactly that flag —
   `factory/roadmap/workflow.py:864` — `_run_inner` builds the dispatchable list
   and tests `readiness.spec(entry.spec_dir).dispatchable` at
   `factory/roadmap/workflow.py:867` — `_run_inner` — and
   `factory/roadmap/workflow.py:1294` — `_dispatch` starts a child epic for each
   survivor: an agent in a worktree, tokens spent, a pull request opened, the
   landing branch moved.
4. The interval between the edit and that dispatch is one tick.
   `factory/verify/models.py:235` — `RoadmapDials` defaults `cadence_s` to 300,
   and the corpus is re-read from the filesystem every pass:
   `factory/roadmap/workflow.py:494` — `read_corpus_activity` calls `read_roadmap`
   against the worker host's own `specs/` directory.
5. So the act is unrefusable by construction, and it is also unvalidated. The
   verdict it ought to be conditioned on cannot be reached by a program at all:
   `factory/cli/nouns/spec.py:490` — `_validate_command` takes an
   `argparse.Namespace`, prints, and returns an exit code;
   `factory/cli/nouns/spec.py:275` — `validate_spec_command` is a wrapper over
   it; and even in-tree the only other consumer reaches it by argv, at
   `factory/cli/install.py:1078` — `_spec_validate_argv`.
6. The one transition the system does offer is ephemeral and needs a live run.
   `factory/roadmap/workflow.py:621` — `promote_spec` treats a named draft as
   ready **for one pass, in memory**, and
   `factory/roadmap/workflow.py:1110` — `_apply_promotions` says in its own
   docstring that the file remains the authority of record. It covers the gap
   until the next edit; it is not a way to make the edit.

**The second precondition is already a value, and is already read three ways.**
`factory/roadmap/models.py:570` — `compute_readiness` answers "is every
`depends_on_landed` edge satisfied" over an injected resolver, and the three
callers inject three different ones: `factory/roadmap/cli.py:63` —
`render_command` injects none, so `ergane spec list` reads attestation only;
`factory/cli/status.py:292` injects `factory/cli/status.py:441` —
`_observed_landed_resolver`, backed by the repository's landing history; and the
roadmap workflow injects its own. A verb that writes its own fourth resolver
permits flips the roadmap then refuses, which is the exact disagreement the
acceptance criteria below forbid.

**And the assumption behind the gap is deliberate, which is why this spec gives
the declaration a seam rather than overturning it.**
`factory/roadmap/models.py:66` — `SpecState`'s docstring calls `ready` "the
operator's declaration" and closes at `factory/roadmap/models.py:79` —
`SpecState` with "intent is declared, progress is observed". That holds. What
does not follow from it is that the declaring must happen in an editor, with no
grammar, no preconditions and no record.

## The rule this spec is asking for

**Readying a spec and deferring one are library functions with a plan and an
apply: the plan computes the exact bytes and refuses what the roadmap would
refuse, and the apply writes them atomically or refuses because the file moved.**

The verb names follow `CONTEXT.md:243`, which resolves "promote" to the
operator's fast-forward of `main` and names the draft-to-ready transition
**ready a spec**.

The transition table, complete. "permitted" means the plan carries a change; a
refusal carries a layer, and the layer is how a program tells "nothing to do"
from "not allowed" from "the preconditions are unmet" from "the preconditions
could not be checked".

| declared state | requested | result |
|---|---|---|
| `draft` | `ready` | permitted **iff** the validation report carries no refusal and no skipped layer **and** every `depends_on_landed` edge is satisfied |
| `deferred` | `ready` | the same preconditions |
| `ready` | `ready` | refused at layer `transition` — already declared, nothing to write |
| `landed` | `ready` | refused at layer `transition` — an attestation is not re-opened here |
| `draft` | `deferred` | **permitted, unconditionally** — parking a spec has no preconditions |
| `ready` | `deferred` | permitted, unconditionally |
| `deferred` | `deferred` | refused at layer `transition` |
| `landed` | `deferred` | refused at layer `transition` |
| any | anything else | refused at layer `transition` — this spec ships no way to write `landed` or `draft` |
| no frontmatter fence pair | either | refused at layer `frontmatter` — there is no `state:` line to edit |
| the validation report carries a skipped layer | `ready` | refused at layer `validate_skipped` — a layer that did not run refused nothing |
| the corpus does not parse | `ready` | refused at layer `corpus` — the edge question cannot be answered over a corpus `read_roadmap` refuses |

Two functions own those rows. The shared planning function of FR-002 owns every
row that turns on the declared and the requested state alone: the six
`transition` rows, the `frontmatter` row and the catch-all. The ready planner
adds the four precondition layers on top of it — `validate` (FR-009),
`validate_skipped` (FR-017), `depends_on_landed` (FR-010) and `corpus` (FR-018)
— which is why the first two rows read "permitted **iff**" rather than
"permitted", and why the defer planner reaches none of them.

Each precondition layer emits **one refusal per fault, not one per layer**, and
because a `StateRefusal` carries one layer name and one message (FR-001), the
report's own layer name rides at the head of the message: a `validate` refusal
reads `<the report layer>: <the report message>` and a `validate_skipped`
refusal reads `<the skipped layer>: <the reason it did not run>`. FR-009 and
FR-017 fix that rendering so two implementations cannot each satisfy their own
tests and print different things to the operator.

### What this spec is not

It is not an attestation verb. `spec attest` came off this docket by the
consumer's own narrowing, and `state: landed` keeps the meaning
`factory/roadmap/models.py:66` — `SpecState` gives it.

It is not a change to what `ready` means. `factory/roadmap/models.py:607` —
`compute_readiness` still decides dispatchability, and this verb refuses exactly
what that function would report as a blocker — through that function, never
beside it.

It is not a replacement for `factory/roadmap/workflow.py:621` — `promote_spec`.
The signal covers the gap until an edit is made; this verb makes the edit. Both
stay, and no workflow file is touched.

It is not a widening of the frontmatter grammar. The key set stays closed at
`factory/roadmap/models.py:117`, and the change this verb writes touches exactly
one line of a block that already exists.

## User Scenarios & Testing

The four stories are written in the order they must land — US1, US2, US4, US3 —
which is why the numbers do not run in sequence: US4 is the half of the original
US2 that was split off when the pair was measured against the diff bound
(D-050), and an existing story number is never re-used for different work.

### User Story 1 - The change is bytes, computed before anything is written (Priority: P1)

As a program that wants to flip a spec's state, I can obtain the exact bytes that
would be written, show them to a human, and then write them — and be refused if
the file moved while the human was looking.

**Why this priority**: P1, and everything else rests on it. A caller that can only
write cannot put the bytes in front of a human before writing them, which is what
makes today's editor edit dangerous; and a caller that re-reads between the
preview and the write races the operator's own editor session, which on this floor
runs at the same time on the same tree.

**Independent Test**: Plan a change over a fixture spec directory and read the
returned value; apply it, and apply a second one after editing the file underneath
it.

**Acceptance Scenarios**:

1. **Given** a `spec.md` whose frontmatter declares `state: draft` and carries
   provenance comment lines, a `depends_on_landed:` list and a `fixes:` list,
   **When** a change to `ready` is planned, **Then** the returned value carries
   that path, `draft` as the declared state, `ready` as the requested state, and a
   text whose only differing line is the `state:` line — proven by a committed
   test that removes that one line from each of the two texts and asserts the
   remainders are equal, so a diff that re-rendered the block from parsed YAML
   fails on the comment lines.
2. **Given** the same fixture, **When** a change is planned that is permitted and
   then a second one that is refused, **Then** the file's bytes are identical to
   what they were before either call — asserted by a committed test that hashes
   the file before and after both.
3. **Given** a planned change, **When** the file is rewritten between the plan and
   the apply, **Then** the apply writes nothing and returns a refusal naming the
   path and both digests, and the file still holds the rewritten bytes — asserted
   by a committed test that performs the rewrite between the two calls.
4. **Given** a planned change whose file has not moved and an `os.replace` that
   raises, **When** it is applied, **Then** the spec file still holds its original
   bytes — asserted by a committed test that patches `os.replace`, which a direct
   write onto the target path cannot satisfy.
5. **Given** a `spec.md` with no leading fence pair, and separately one declaring
   `state: landed`, **When** a change to `ready` is planned for each, **Then** the
   first is refused at layer `frontmatter` and the second at layer `transition`,
   each naming both states or the path, and neither file is written — asserted by
   one committed test over the pair.

### User Story 2 - The readiness resolver moves once, and both readers hold the same object (Priority: P2)

As the operator who has to trust two commands at once, the reading of "landed"
that `ergane status` shows me and the reading the ready verb will refuse on are
one function in one place, not two that agree today.

**Why this priority**: P2, and it is deliberately a relocation and nothing else.
It is the story that makes the fourth reading of readiness impossible to write
by accident, and it is the only story that edits a module three other draft specs
also anchor into — so it is small, it is separable, and it is taken before any
behaviour is built on top of it.

**Independent Test**: Import each moved name from `factory.cli.status` and from
its new home and compare identity; read `compute_readiness`'s signature and the
source of `factory/roadmap/models.py`.

**Acceptance Scenarios**:

1. **Given** the six relocated names — the observed resolver, the basis type, the
   function that chooses the basis, the observed-landing reader and the two
   helpers they read — **When** each is imported from `factory.cli.status` and
   from its new home under `factory/spec/`, **Then** the two names are the same
   object for every one of the six, and the diff edits neither
   `tests/test_both_verbs_agree_about_the_schedule.py` nor
   `tests/test_ergane_status.py` — asserted by one committed test that imports
   each name from both modules and asserts identity, so a copy rather than a move
   fails it.
2. **Given** `factory/cli/status.py` and the new module under `factory/spec/`
   after the move, **When** the resolver `factory/cli/status.py:292` injects into
   `factory/roadmap/models.py:570` — `compute_readiness` is traced back to where
   it is defined, **Then** there is exactly one definition site for the six names
   and it is the new one — `factory/cli/status.py`'s own module body carries no
   `def` and no `class` statement for any of them, only the import that re-binds
   them, and `_readiness_basis` and `_observed_landed_resolver` each report a
   `__module__` under `factory.spec`, the module FR-019 sends the ready planner
   to, so the reading `ergane status` shows and the reading the ready verb will
   refuse on are one function in one place; **and**, as a second clause,
   `compute_readiness` still takes `landed_for` and `drifted_for` as parameters,
   `factory/roadmap/models.py` imports no `subprocess`, no
   `factory.workgraph.landed` and no `factory.workgraph.worktree` and holds no
   `["git", ...]` argv literal, while the `from factory.workgraph.models import
   find_cycle` that `factory/roadmap/models.py:53` already carries survives —
   asserted by two committed tests: the first is false against this tree and true
   only once the definitions have moved, and the second is a control that reads
   the signature with `inspect.signature` and the imports with `ast`, so a git
   read pushed down into the readiness computation fails it and deleting the
   corpus cycle detector to satisfy it fails too.

### User Story 4 - Readying refuses exactly what the roadmap would refuse (Priority: P3)

As an operator, the verb that arms the most expensive act in the product tells me
why it will not, and names the edge that is not satisfied.

**Why this priority**: P3, and it depends on US1 for a plan shape to carry
refusals and on US2 for the resolver it injects. This is the story that turns an
unrefusable edit into a refusable one, and it is where the disagreement hazard
lives: two implementations of "what ready means" is worse than none.

**Independent Test**: Plan a ready change over a spec whose trio validates clean
and whose edges are satisfied, then over one whose trio refuses, then over one
whose edge names a spec that declares `draft`, then over the clean one again with
an unreadable target repository, then over a corpus holding a spec that does not
parse; read the refusals and their layers.

**Acceptance Scenarios**:

1. **Given** a corpus holding a draft spec whose trio validates clean with every
   layer run and whose every `depends_on_landed` edge names a spec attesting
   `landed`, **When** a ready plan is computed, **Then** it is permitted, carries
   a change to `ready`, and carries the readiness basis the relocated resolver
   reported — asserted by a committed test.
2. **Given** a draft spec whose trio the validation report refuses, **When** a
   ready plan is computed, **Then** it carries no change and one refusal at layer
   `validate` **per refusal in that report**, each carrying as its message that
   refusal's own layer name, a colon and a space, and that refusal's own message —
   asserted by a committed test that calls the validation library form over the
   same directory, renders its refusals into that form, and compares the two
   sequences in order, so neither a hand-written summary string nor a collapse to
   one refusal per layer can satisfy it.
3. **Given** a draft spec declaring `depends_on_landed` on a spec whose own
   frontmatter declares `draft`, **When** a ready plan is computed, **Then** it
   carries no change and a refusal at layer `depends_on_landed` naming that spec
   directory and the state it declares — and the same committed test asserts that
   the blockers the readiness computation reports for that spec are exactly the
   directories the refusals name, so a second implementation of the edge rule
   cannot pass.
4. **Given** one spec directory that fails both preconditions — its trio refuses
   and its edge is unmet — **When** a ready plan and a defer plan are computed over
   it, **Then** the ready plan is refused and the defer plan is permitted and
   carries a change to `deferred` — asserted by one committed test over the pair,
   so wiring the preconditions into the shared planner fails.
5. **Given** the same clean spec of scenario 1 and a target repository path that
   is not a readable directory, **When** a ready plan is computed, **Then** it
   carries no change and one refusal at layer `validate_skipped` per skipped layer
   — `anchor_resolution`, `symbol_anchors` and `evidence` — each carrying as its
   message that layer's own name, a colon and a space, and the reason the
   validation report gives for not running it, while the same plan over the same
   corpus with a readable target repository is permitted — asserted by one
   committed test that computes both plans and asserts the pair, so a planner that
   reads only the report's refusals fails it.
6. **Given** a corpus holding, beside the draft spec being readied, one spec whose
   own frontmatter does not parse, **When** a ready plan is computed for the draft
   spec, **Then** the call returns a plan refused at layer `corpus` carrying each
   fault the corpus reader names, and raises nothing — asserted by a committed
   test that fails with the corpus reader's own exception if the planner lets it
   through.

### User Story 3 - The operator reaches it through a verb that shows before it writes (Priority: P4)

As an operator, `ergane spec ready <dir>` prints what it would write, writes it,
and exits non-zero with a reason when it will not.

**Why this priority**: P4 and it depends on US4. The library form is the
deliverable; this is the door a human uses, and it is deliberately thin so that
what a human sees and what a program computes cannot drift.

**Independent Test**: Run the two verbs over a fixture corpus, with and without
the preview flag, over a spec that is permitted and one that is refused, and once
with no `--target-repo` at all.

**Acceptance Scenarios**:

1. **Given** a fixture corpus holding a spec the library form permits, **When**
   the ready verb is invoked with `--dry-run`, **Then** it exits 0, its output
   carries the `state:` line it would write and the digest the change was computed
   against, and the file's bytes are unchanged — asserted by a committed test that
   hashes the file around the call.
2. **Given** the same spec, **When** the ready verb is invoked without
   `--dry-run`, **Then** the file's frontmatter declares `ready`, every comment
   line and both list keys are byte-identical to before, and the output names the
   transition — asserted by a committed test.
3. **Given** a spec the library form refuses, **When** the ready verb is invoked,
   **Then** it exits with the user-error code, its output carries one line per
   refusal carrying that refusal's layer and its message, and the file is
   unchanged — asserted by a committed test.
4. **Given** the same refused spec, **When** the verb is invoked with `--json`,
   **Then** the printed document carries the declared state, the requested state,
   each refusal with its layer and message, and a flag stating nothing was written
   — asserted by a committed test that loads the document and reads those fields.
5. **Given** the `spec` noun's parser, **When** its registered subcommand names
   are read, **Then** they include `ready` and `defer`, and the module docstring,
   the `spec` parser's help string and the `NOUN` summary each name every
   registered subcommand — asserted by one committed test that derives the
   expected set from the parser rather than restating it, which today's help
   string at `factory/cli/nouns/spec.py:114` — `_add_spec_parser` already fails
   because it omits `new`.
6. **Given** a fixture corpus whose specs root sits inside a git repository and a
   command line carrying no `--target-repo`, **When** the ready verb runs, **Then**
   the target repository handed to the planner is that repository — asserted by a
   committed test that patches the planner, reads the argument it was called with,
   and asserts it equals the repository holding the specs root, so a verb that
   copied `validate`'s literal default fails.

## Functional Requirements

- **FR-001**: `factory/spec/` MUST export a frozen `SpecStateChange` carrying the
  spec directory, the path of the `spec.md` it was computed for, the state that
  file declares, the state requested, the complete text the file would hold, and
  the SHA-256 hex digest of the bytes it was computed against; a frozen
  `StateRefusal` carrying a layer name and a message; and a frozen
  `SpecStatePlan` carrying the spec directory, the declared and requested states,
  an optional change and a tuple of refusals, permitted exactly when it carries a
  change and no refusal.
- **FR-002**: A planning function MUST return a `SpecStatePlan` for a spec
  directory and a requested state and MUST NOT write; a committed test asserts the
  file's bytes are unchanged after a permitted plan and after a refused one.
- **FR-003**: A change's text MUST differ from the text read in exactly one line —
  the frontmatter's `state:` line — with every other byte identical, including
  every `#` comment line in the block, their order, the `depends_on_landed:` and
  `fixes:` blocks, and the file's trailing newline. The proof MUST be a committed
  test over a fixture whose frontmatter carries all three, asserting the two texts
  are equal once that line is removed from each.
- **FR-004**: The transition table in "The rule this spec is asking for" MUST
  hold, row for row. Every refusal MUST carry the layer its row names, and every
  refusal at layer `transition` MUST carry a message naming both the declared and
  the requested state.
- **FR-005**: A `spec.md` carrying no leading `---` fence pair MUST be refused at
  layer `frontmatter` naming the path, because
  `factory/roadmap/models.py:240` — `_split_frontmatter` reads such a file as
  `draft` and there is no `state:` line to edit.
- **FR-006**: The apply function MUST re-read the target file, hash its bytes, and
  when the digest differs from the change's MUST write nothing and return a
  refusal naming the path and both digests.
- **FR-007**: The write MUST go through a temporary file inside the spec's own
  directory followed by `os.replace`, following
  `factory/registry.py:353` — `_write_document`, so no reader ever observes a
  partially written `spec.md`; proven by a committed test that makes `os.replace`
  raise and asserts the file still holds its original bytes.
- **FR-008**: `factory/spec/` MUST export a ready planner and a defer planner as
  the two named entry points, each returning a `SpecStatePlan` and each obtaining
  the transition-table answer from the single planning function of FR-002 rather
  than restating it.
- **FR-009**: The ready planner MUST refuse when the spec's validation report
  carries any refusal, with one `StateRefusal` at layer `validate` **per refusal
  in that report** — not one per refusing layer, because a single layer emits one
  finding per bad anchor (`factory/cli/nouns/spec.py:993` —
  `_check_symbol_anchors`) and one per corpus fault
  (`factory/cli/nouns/spec.py:1004` — `_check_frontmatter`), and a collapse to one
  refusal per layer discards every message but one. Because a `StateRefusal`
  carries one layer name and one message (FR-001), the refusal's layer MUST be
  `validate` and its message MUST be that report refusal's own layer name, then
  `": "`, then that refusal's own message, in the report's order — one rendering,
  so the operator's line and a program's field agree. The report MUST be obtained
  by calling the validation library form 133 exports, not by re-composing layers
  and not by running the command-line verb the way
  `factory/cli/install.py:1078` — `_spec_validate_argv` does.
- **FR-010**: The ready planner MUST refuse when any `depends_on_landed` edge is
  unsatisfied, with one `StateRefusal` at layer `depends_on_landed` per unmet edge
  naming the spec directory and the state that spec's own frontmatter declares.
  The unmet set MUST be taken from `factory/roadmap/models.py:570` —
  `compute_readiness` over the corpus `factory/roadmap/models.py:411` —
  `read_roadmap` returns, never from a second implementation of the same rule.
- **FR-011**: `factory/cli/status.py:441` — `_observed_landed_resolver`, the
  observed resolver `ergane status` injects, MUST move into `factory/spec/`
  together with `factory/cli/status.py:247` — `ReadinessBasis`,
  `factory/cli/status.py:378` — `_readiness_basis`,
  `factory/cli/status.py:469` — `_observed_landing` and the two helpers they read,
  `factory/cli/status.py:425` — `_repo_holding` and
  `factory/cli/status.py:491` — `_declared_story_keys` — and with the two
  module-level imports those functions read, which move as imports and not as
  definitions: `landing_branch` at `factory/cli/status.py:110` and `_landing_head`
  at `factory/cli/status.py:106`, which is an alias of
  `factory.workgraph.landed._resolve_default_head` and not a local helper anyone
  can find by searching for a `def`. Every moved name MUST be re-bound in
  `factory/cli/status.py` under the name it has today, so no call site, no
  construction site and no test import in that module changes. No git read may be
  added inside `factory/roadmap/models.py:570` — `compute_readiness`, whose
  resolvers are documented as injected at
  `factory/roadmap/models.py:587` — `compute_readiness` precisely so git stays out
  of workflow code; the import that module already carries at
  `factory/roadmap/models.py:53`, `from factory.workgraph.models import
  find_cycle`, is the corpus cycle detector `factory/roadmap/models.py:374` —
  `_cross_validate` calls and MUST survive this story untouched.
- **FR-012**: The defer planner MUST NOT consult the validation report, the
  skipped layers, the corpus or the edges; a committed test MUST plan both over
  one spec directory that fails both preconditions and assert ready is refused
  while defer is permitted.
- **FR-013**: `ergane spec ready <spec-dir>` and `ergane spec defer <spec-dir>`
  MUST be registered beside the five verbs `factory/cli/nouns/spec.py:113` —
  `_add_spec_parser` already adds, each a thin wrapper that calls its planner,
  renders the plan and — unless the preview flag is given — calls the apply
  function. Neither verb may hold precondition logic of its own. The ready verb
  MUST take `--specs-root` with the same default
  `factory/cli/nouns/spec.py:134` gives `validate`, and `--target-repo` defaulting
  to the repository holding that specs root — the relocated
  `factory/cli/status.py:425` — `_repo_holding` of FR-011 — and never to the
  literal default `validate` carries, which the tree itself describes at
  `factory/cli/nouns/spec.py:1198-1200` as a path most hosts do not carry. When no
  repository holds the specs root and no `--target-repo` is given, the verb MUST
  refuse naming that rather than run against a path that does not exist.
- **FR-014**: `--dry-run` MUST print the `state:` line the change would write and
  the digest it was computed against, exit 0, and write nothing.
- **FR-015**: `--json` MUST print one document carrying the declared state, the
  requested state, each refusal with its layer and message, and whether anything
  was written.
- **FR-016**: A plan carrying refusals MUST exit with the CLI's user-error code
  and print one line per refusal carrying that refusal's layer and its message —
  which for the precondition layers means the report's own layer name is read back
  to the operator at the head of the message (FR-009, FR-017); and the three
  strings that name this noun's verbs — the module docstring at
  `factory/cli/nouns/spec.py:1`, the parser help at
  `factory/cli/nouns/spec.py:114` — `_add_spec_parser` and the summary at
  `factory/cli/nouns/spec.py:236` — MUST each name every registered subcommand,
  asserted by a committed test that derives the expected set from the parser.
- **FR-017**: The ready planner MUST refuse when the validation report carries any
  skipped layer, with one `StateRefusal` at layer `validate_skipped` per skipped
  layer whose message is that layer's own name, then `": "`, then the reason the
  report gives for not running it — the same rendering FR-009 fixes, for the same
  reason. A layer that did not run refused nothing, and a verdict assembled from
  nine of twelve layers is not "validate clean" — the three layers that skip on an
  unreadable target repository, `factory/cli/nouns/spec.py:904` —
  `_check_symbol_anchors`, `factory/cli/nouns/spec.py:1206` —
  `_check_anchor_resolution` and `factory/cli/nouns/spec.py:1816` —
  `_check_evidence`, are exactly the three that catch a stale anchor. The skipped
  set MUST be read from the report's own skipped member, which 133 FR-002 holds
  separately from the refusals, and never re-derived.
- **FR-018**: The ready planner MUST refuse rather than raise when the corpus does
  not parse. `factory/roadmap/models.py:411` — `read_roadmap` raises naming every
  fault anywhere in the corpus and yields no partial roadmap, so one malformed
  sibling spec makes the edge question unanswerable; each fault it names MUST
  become a `StateRefusal` at layer `corpus`, and the planner MUST return a plan
  rather than propagate the exception.
- **FR-019**: The ready planner MUST obtain its `landed_for` resolver from the
  relocated `factory/cli/status.py:378` — `_readiness_basis` of FR-011 — the
  function that chooses between the observed reading and the degraded
  attestation-only one — and MUST inject exactly that resolver into
  `factory/roadmap/models.py:570` — `compute_readiness`, never a fourth resolver
  written for this verb. The plan MUST carry the `ReadinessBasis` that function
  reported, so a refusal can say which facts decided it.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-011]
US4:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-008, FR-009, FR-010, FR-012, FR-017, FR-018, FR-019]
US3:
  depends_on: []
  depends_on_merged: [US4]
  implements: [FR-013, FR-014, FR-015, FR-016]
```

A chain of three `depends_on_merged` edges, each declared rather than left
inferred (069-US2 FR-007). US2 relocates into the module US1 creates, so the two
would otherwise rewrite one new file concurrently — the collision shape that
passes every pull request's own check and fails in the merge group. US4 adds the
four precondition layers to the plan shape US1 defines, and injects the resolver
US2 moved: it cannot be written before either. US3 renders the plan US4 returns,
and depends on US4 for a fact as well as a shape — FR-013's `--target-repo`
default is the `_repo_holding` that FR-011 relocates and FR-019 consumes. The
edges also order the risk correctly: US1 is pure bytes with no dependency on
133's package beyond its existence, US2 is a move with no new behaviour and is
the only story that edits `factory/cli/status.py`, US4 is the story that must not
invent a second reading of readiness, and US3 is the thinnest and is taken last,
when there is a plan worth rendering. The split of the original US2 into US2 and
US4 is a sizing decision as much as a sequencing one: measured against this
tree, the relocation and the preconditions together approach the deterministic
diff refusal (D-050), and § Sizing in `plan.md` carries the numbers.
