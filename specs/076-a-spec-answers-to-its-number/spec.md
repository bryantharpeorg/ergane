---
state: draft
depends_on_landed:
  - 133-spec-validate-has-one-implementation-and-two-faces
# Drafted 2026-08-20 2:00 PM CT by an operator session, from the operator's own
# ask and from a session that had just spent a day typing
# `specs/075-a-stronger-rung-runs-a-stronger-model` by hand, repeatedly, into
# four different verbs.
#
# DO NOT FLIP READY without a pre-dispatch review.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04-tail);
# every anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at
# 602a92c. The draft was fifteen days and roughly forty landings old and eleven
# of its citations were refusals; seven of those were symbol-tier, two naming
# symbols that now live elsewhere.
#
# THE SPEC CONTRADICTED ITSELF ABOUT WHAT A NUMBER IS, AND THE PLAN TAUGHT THE
# DANGEROUS HALF. FR-002 asked for the leading numeric segment with leading
# zeros optional — integer equality — while FR-003, US1-S4 and the plan's trap 1
# described PREFIX matching ("`07` matches ten specs in this corpus"). Under
# integer equality `07` is the number seven and matches at most one directory.
# An implementer resolving the contradiction the plan's way ships prefix
# matching, which is the one design that can silently derive the wrong spec —
# the failure trap 1 exists to prevent. The tree already answers it: the writer
# half of the same identity rule, `_pick_spec_number`, matches `^(\d+)-` and
# refuses only when two directories claim one number. FR-002 and FR-003 now say
# integer equality out loud, a new US1-S5 pins the no-prefix rule as a refusal,
# and the ambiguity scenario is a duplicate-number corpus rather than a prefix.
#
# THE VERB INVENTORY GREW AND THE PLAN STILL SAID THREE. Spec 106 landed
# `build ship` on 2026-08-25; it takes `spec_dir`, does its own bare
# `Path(args.spec_dir)` and computes `epic_id` from it, in a different noun
# module. A resolver wired only at the three sites the plan named leaves
# `ergane build ship 076` dispatching an epic called `076`. FR-001 now
# enumerates four verbs, FR-013 requires the resolved value be the real
# directory at every one, and US1-S8 asserts the epic id.
#
# ONE INSTRUCTION WOULD NOW BREAK A LANDED FIX. The old trap 3 said to join
# `--specs-root`. Since then `workgraph/derive-resolves-specs-root-against-the-
# cwd-not-the-target-repo` was fixed by comparing `args.specs_root` against the
# default STRING and, when it is untouched, taking the spec directory's own
# parent. A resolver that rewrites `args.specs_root` to an absolute path flips
# that comparison for every caller, path callers included, and re-opens the
# defect. FR-014 forbids the rebind and US1-S9 is its differential.
#
# FOUR KEYS AND A SCOPE CUT ADDED, NONE REMOVED. `fixes:` stays absent: the
# ledger holds no key for either half of this spec, so nothing is declared.
# `depends_on_landed: [133-…]` is new — 133 rewrites `_validate_command` and
# moves ten layer bodies out of `factory/cli/nouns/spec.py`, so every line
# number below moves with it and two stories would otherwise rewrite the same
# 1,865-line module concurrently. Trap 1 now says re-anchor after 133 lands.
# `## Success Criteria` and `## Assumptions` are gone with the house style
# (126 onward); their content is in the scenarios, the traps and the operator
# verification section. Stories, story numbers and the Work Graph shape are
# unchanged; FR-013 and FR-014 are appended rather than renumbered.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail): the landed read is pinned to
# `fetch=False` so a reporting verb cannot touch the network (FR-008, trap 10,
# T023); FR-011's count is given a real source, a branch and a degrade, because
# the pass trap 13 named holds no landing data at all (FR-011, FR-016, US3-S1,
# US3-S5, traps 13 and 17); US1-S9 is rewritten as the demo-container
# differential, the only shape in which the forbidden rebind is visible; US3-S4
# stops asserting "the output is what it is today" — which its own story
# contradicts — and asserts the row invariant instead; the epic state becomes
# FR-015 and enters `--json`; `build ship` and a bare `spec derive` leave the
# evidence task, which was a write and a dispatch dressed as a read (T015, trap
# 18); US1-S5's proof clause gains the assertion that forces production code;
# and one anchor moves from `factory/cli/nouns/spec.py:298`, the doc comment,
# to `factory/cli/nouns/spec.py:299`, the regex. Two existing suites are named
# to extend rather than re-invent.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail), after an adversarial review
# refuted the trio at 602a92c. The `07` probe is gone from the evidence task and
# from the operator sequence: `specs/007-parallel-dispatch` exists, and under
# this spec's own FR-002 `int('07') == 7` resolves to it, so demanding a refusal
# for `07` against the live corpus contradicted FR-002 and US1-S2 — the probe
# now proves the resolution and uses `999`, which no directory claims, for the
# miss (T015, plan step 2; plan step 5's empty-state check was wrong the same
# way and is now run on a copy). US3's evidence is trimmed to excerpts and the
# Sizing paragraph names US3, not US1, as the story whose evidence competes with
# its code — one corpus render is a measured 144 rows and 11,965 bytes (T036).
# Trap 2's worked failure is rebuilt on a corpus where a prefix matcher really
# does pick one wrong directory. `show` registers `--default-branch` so FR-008's
# first arm exists at all (FR-008, T022, T023), and takes its repository from
# `_repo_holding`, which works inside a node's worktree. FR-007 and a new
# US2-S7 say out loud that `show` takes a number, which no criterion said. T009
# is labelled **The control**. Trap 1 no longer claims 133's NOT IN SCOPE
# excludes the `validate` parser. Four load-bearing symbol citations are
# unwrapped onto one line so the tier can machine-check them.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail, cross-batch): three blocking
# defects a completeness critic confirmed against the tree at 602a92c. Trap 8
# asserted that `factory/cli/nouns/build.py` must not import
# `factory/cli/nouns/spec.py`. It already does: `factory/cli/nouns/build.py:1031`
# is a deferred `from factory.cli.nouns.spec import derive_spec_command,
# validate_spec_command` inside `ship_command`, landed by 106-US4, three lines
# above the `factory/cli/nouns/build.py:1034` anchor T013 sends the implementer
# to edit — so the plan handed that implementer a rule under which deleting a
# landed `build ship` import reads as obedience, and breaking one of the four
# verbs FR-001 is about. Trap 8 now says the import is landed and must be left
# alone, and keeps its conclusion on the grounds that already carried it; T025
# drops the same false reason and keeps the true one.
#
# FR-008 now requires `show`'s landed read to live in one named, per-spec-cached
# reader. FR-011 says US3's landed half comes from "the reader US2 builds for
# FR-008" and forbids a second implementation, while the plan's US2 sizing
# paragraph said US2 "writes no new reader" and its US3 paragraph then reused
# "the cached per-spec reader US2's `show` already uses" — two halves of one
# section contradicting each other, with a judged criterion resting on the false
# one. FR-011 is the criterion, so US2 builds the object; both sizing paragraphs
# now say the same thing and T023 names it.
#
# US3-S2 gains its positive half. It asserted only that a draft spec's directory
# name is absent, which an always-empty `--state` satisfies alongside US3-S3 and
# US3-S5, and which argparse makes green the moment the flag parses — a
# do-nothing diff exits `SystemExit(2)` with empty stdout, so the absence holds
# there too. It now asserts the matching row survives, the non-matching one does
# not, and the row count equals the number of ready specs. This is the fix
# US1-S5 already carries, applied where the same shape was left standing.
#
# WHERE THIS CAME FROM. The operator's own ask, plus the measured day spent
# typing `specs/075-a-stronger-rung-runs-a-stronger-model` by hand into four
# verbs and the runbook line that exists only because the argument is a path.
# Nothing in the ledger reports it; it is an ask, not a defect sighting.
#
# WHAT IT COST, MEASURED. Nothing, and that is the honest answer: this spec
# closes no finding. All 520 ledger rows were read at 602a92c and none names
# either half — no key about a spec verb taking a path rather than a number, and
# none about the absence of a per-spec view. The two nearest,
# `workgraph/derive-resolves-specs-root-against-the-cwd-not-the-target-repo` and
# `interpreter/specs-root-is-compiled-relative-and-resolved-against-the-workers-
# cwd`, are both RESOLVED and are what FR-014 exists to keep closed rather than
# to fix; declaring either would be over-declaration. One open key,
# `cli/spec-derive-json-rewrites-the-committed-artifact`, is corroboration for
# trap 18 and is not fixed here.
#
# NOT IN SCOPE. `## Success Criteria` and `## Assumptions` (dropped with the
# house style; their content is in the scenarios, the traps and the operator
# verification section). Prefix, fuzzy and slug matching. Ownership — which
# specs an instance manages versus which merely exist in a tree. Any change to
# the path form: every existing script, runbook and roadmap call passes a path
# and keeps behaving byte-identically, and US1-S3 is the control that says so.
---

# Feature Specification: a spec answers to its number

**Created**: 2026-08-20
**Depends on**: `133-spec-validate-has-one-implementation-and-two-faces`, landed.

## The gap, stated precisely

Specs are numbered. Nothing accepts the number.

```
$ ergane spec validate 075
ergane: cannot read 075/spec.md: [Errno 2] No such file or directory
```

The chain is four steps, and the fourth is the one that grew:

1. Every verb that takes a spec registers a positional `spec_dir` and describes
   it as a directory: `factory/cli/nouns/spec.py:137` — `_add_spec_parser` for
   `validate`, `factory/cli/nouns/spec.py:159` — `_add_spec_parser` for
   `derive`, `factory/cli/nouns/spec.py:219` — `_add_spec_parser` for `landed`,
   and `factory/cli/nouns/build.py:2111` — `add_parser` for `build ship`.
2. Every handler turns that string into a path with a bare `Path()`, with no
   resolution and no specs-root join:
   `factory/cli/nouns/spec.py:491` — `_validate_command`,
   `factory/cli/nouns/spec.py:256` — `_derive_command`,
   `factory/workgraph/cli.py:175` — `landed_command`,
   `factory/workgraph/cli.py:307` — `derive_command`, and
   `factory/cli/nouns/build.py:1034` — `ship_command`.
3. So the operator types `specs/075-a-stronger-rung-runs-a-stronger-model` in
   full, four times, for four verbs, and a spec's identity in conversation
   ("075") is not its identity at the command line.
4. The runbook already carries the scar tissue: *"`spec derive` takes the full
   path, not the feature name — `--specs-root` is not joined for you. Getting
   this wrong prints `cannot read 070-…/spec.md` and silently leaves the
   previous graph in place."* That is a documented trap that exists only because
   the argument is a path.

**The reader half of the identity rule is missing; the writer half is already
here.** `spec new` mints a number by walking the specs root, matching
`^(\d+)-` and refusing when two directories claim one value —
`factory/cli/nouns/spec.py:302` — `_pick_spec_number`, reading the pattern at
`factory/cli/nouns/spec.py:299`. Nothing reads a number back.

## And there is no way to look at one spec

`ergane spec list` renders every spec with its state and blockers
(`factory/roadmap/cli.py:46` — `render_command`, rendered at
`factory/roadmap/cli.py:92` — `_render_roadmap`). `ergane status` joins the
whole floor — corpus, running epics, ready queue, drafts, pace — at
`factory/cli/status.py:284` — `collect_floor`. Both are corpus views. Neither
narrows to one spec, and `factory/cli/status.py:861` — `add_status_parser`
takes a specs root and a `--json` flag and no spec.

To answer "what is going on with 075" an operator today runs `spec list` and
greps, then `spec landed` with `--default-branch` remembered correctly, then
`build status` against an epic id they assemble by hand, then reads the
frontmatter for the hold note. Four commands and a paste, for one spec.

The information is all there. Nothing collects it for one spec.

## The rule this spec is asking for

**A spec's number is a name the CLI accepts wherever it accepts a spec
directory — resolved by integer equality on the directory's leading numeric
segment, never by prefix, and never in place of an argument that already names
a directory.**

The five cases, complete:

| argument names an existing directory | numeric value of the argument | result |
|---|---|---|
| yes | — | that directory, byte-identically to today; no resolution runs |
| no | matches exactly one direct child of the specs root | that directory |
| no | matches more than one | **refused**, naming every candidate |
| no | matches none | **refused**, naming the value and the root searched |
| no | the argument is not all digits | **refused** exactly as today |

Two consequences the table makes explicit and the draft got wrong. `07` is the
number seven: in a corpus holding `070-…` and `071-…` and nothing numbered 7 it
resolves to nothing and is refused — it never picks `070-…`. And the
more-than-one row is reachable only from a corpus where two directories claim
one number, which is the same corpus defect
`factory/cli/nouns/spec.py:302` — `_pick_spec_number` already refuses to mint
into.

### What this spec is not

It is not a change to the path form. Every existing script, runbook and roadmap
call passes a path and keeps behaving identically; this adds an accepted form
and removes none.

It is not prefix matching, fuzzy matching, or slug matching. A number is a
number. Resolving `07` to `070-…`, or `stronger` to `075-…`, is out of scope and
FR-002 forbids the first outright.

It is not ownership. Which specs a factory instance *manages* versus which
merely exist in a tree is a separate question — it becomes real when Ergane is
installed into a brownfield repo it did not bootstrap, and it touches the
registry and install rather than the spec verbs.

It is not a writer, and it is not a fetcher. `show` dispatches nothing, writes
nothing, creates no directory, needs no confirmation and touches no network —
the four properties `factory/cli/status.py:284` — `collect_floor` already holds,
the last of them by passing `fetch=False` at
`factory/cli/status.py:483` — `_observed_landing`.

It is not a second status board. `ergane status` keeps answering for the whole
floor; `show` answers for one spec and reuses that module's readers rather than
growing a second set.

## User Scenarios & Testing

### User Story 1 - Every spec verb takes a number (Priority: P1)

As an operator, I can name a spec by its number in any verb that takes a spec,
so the identity I use in conversation is the identity I type.

**Why this priority**: P1 and independently useful. It removes a documented trap
and it is the prerequisite for anyone bothering to use US2.

**Independent Test**: Over a supplied fixture corpus, run each of the four
spec-taking verbs with a number and with the full path and compare what each
operated on; then run one with a duplicate-numbered corpus and read the refusal.

**Acceptance Scenarios**:

1. **Given** a supplied fixture corpus containing
   `075-a-stronger-rung-runs-a-stronger-model`, **When** a spec verb is given
   `075`, **Then** it operates on that directory — proven by a committed test
   over the fixture corpus, never over this repository's own `specs/`.
2. **Given** the same corpus, **When** a verb is given `75`, **Then** it
   resolves the same way; a leading zero is not required — proven by a committed
   test.
3. **Given** the same corpus, **When** a verb is given the full path it takes
   today — including an absolute path whose parent is not the specs root —
   **Then** it behaves exactly as it does today and no resolution is attempted
   — proven by a committed test. This is the control: every existing script and
   runbook passes a path.
4. **Given** a corpus in which two directories claim number 70 — `070-alpha`
   and `70-beta` — **When** a verb is given `70`, **Then** it is refused, naming
   both candidates and never choosing one — proven by a committed test. That is
   the same corpus defect `_pick_spec_number` refuses to mint into.
5. **Given** a corpus containing `070-…` and `071-…` and no spec numbered 7,
   **When** a verb is given `07`, **Then** it is refused, naming `07` **and the
   specs root it searched** — proven by a committed test asserting the refusal
   text carries both the value and that root, and mentions neither `070-…` nor
   `071-…`. The root is the half that forces production code: today's
   do-nothing failure already prints `cannot read 07/spec.md` and names neither
   neighbour. A prefix match would resolve it, and a resolver that prefix-matches
   is one that silently derives the wrong spec.
6. **Given** a corpus with no spec of that number, **When** a verb is given it,
   **Then** the refusal names the number and the specs root it looked in —
   proven by a committed test.
7. **Given** a number and a `--specs-root` that is not the default, **When**
   `spec validate`, `spec derive` or `build ship` runs, **Then** the number
   resolves against that root; and **When** `spec landed` runs, which registers
   no such flag, **Then** the number resolves against the default root — proven
   by a committed test covering both halves. Not joining the flag is the
   documented trap this story removes; assuming every verb has it is the way to
   crash the one that does not.
8. **Given** a number, **When** `spec derive` and `build ship` each run on it,
   **Then** the epic id each computes is the full directory name
   (`075-a-stronger-rung-runs-a-stronger-model`), not `075` — proven by a
   committed test asserting the epic id at both sites. A synthetic path that
   merely reads the right `spec.md` dispatches under a name nothing else
   recognises.
9. **Given** a target repository whose specs directory is not the one under the
   working directory — the demo-container shape — and an **absolute** spec
   directory inside it, **When** `spec derive` runs on that absolute path with
   no `--specs-root`, **Then** the compiled graph's `specs_root` is that
   directory's own parent rather than the decoy root under the working
   directory, and the parsed `--specs-root` value is still the literal default
   string after resolution has run — proven by a committed test extending
   `tests/test_derive_specs_root_default.py` and asserting both. The by-number
   form under the default root cannot catch this: there the rebound value and
   the untouched value are equal by construction, so both implementations pass.

### User Story 2 - One spec's whole picture, in one command (Priority: P1)

As an operator, `ergane spec show <n>` tells me what is true about one spec
without my running four commands and assembling the answer.

**Why this priority**: P1. It is the ask, and it is what the corpus views cannot
do — `spec list` is one line per spec by construction and `ergane status` is the
whole floor.

**Independent Test**: Run `show` over a fixture corpus with a known landing
history, once with a control plane and once with none, and read both reports.

**Acceptance Scenarios**:

1. **Given** any spec, **When** `show` runs, **Then** the report carries the
   state from frontmatter, the story count, the landed count and the task count
   — proven by a committed test asserting all four against a fixture corpus
   whose four values are known and distinct from one another.
2. **Given** a spec whose stories have landed on a landing branch the manifest
   declares and that is not `main`, **When** `show` runs, **Then** the landed
   count is the one read against that declared branch, and it is read **without
   fetching** — proven by a committed test over a fixture repository where the
   two branches hold different landings, so a `main` default returns a different
   number and fails, and by a second assertion that the reader — the named,
   per-spec-cached callable `show` reads through, the one FR-011 makes US3 reuse
   — was called with `fetch=False` and that no `git fetch` was attempted.
3. **Given** a spec that is blocked, **When** `show` runs, **Then** it names the
   blockers, and they are the same values `compute_readiness` gives `spec list`
   for that spec — proven by a committed test asserting the two agree.
4. **Given** no reachable control plane, **When** `show` runs, **Then** it
   reports every fact readable from disk and reports the epic state as unknown
   rather than failing, and the diff shows the failure caught through the named
   guards at `factory/cli/status.py:147` and `factory/cli/status.py:154` (or the
   `OperatorError` the client opener raises) and never through a bare
   `except Exception` — proven by a committed test that drives the no-client path
   and asserts the disk facts are all present.
5. **Given** a reachable control plane and a dispatched epic, **When** `show`
   runs, **Then** it reports that epic's state, read through the `epic_status`
   query on the handle named by `factory/workgraph/cli.py:160` — `workflow_id` —
   proven by a committed test against a fake client, asserting the state
   reported is the one the fake returned and the id queried is
   `epic-<directory name>`.
6. **Given** `--json`, **When** `show` runs, **Then** the document carries the
   same six facts under stable keys — the five disk facts and the epic state,
   which reads `unknown` when no control plane answered — and the human render is
   produced from that same object — proven by a committed test asserting
   field-by-field agreement between the document and the rendered lines, on both
   the reachable and the unreachable path.
7. **Given** the fixture corpus of US2-S1, **When** `show` is given the spec's
   number and then, in a second run, that spec's directory path, **Then** the
   two `--json` documents are equal — proven by a committed test asserting that
   equality, so `show` is held to the resolver FR-002 requires and a `show` that
   accepts only a path fails.

### User Story 3 - The corpus view answers "what should I look at" (Priority: P2)

As an operator, `ergane spec list` shows me progress and lets me filter, so the
list is a work queue rather than an inventory.

**Why this priority**: P2. `list` works today; this makes it answer the question
an operator actually brings to it.

**Independent Test**: Render a fixture corpus unfiltered, filtered to a state
that matches, and filtered to a state that matches nothing, and compare the
three; then render a corpus no git repository holds.

**Acceptance Scenarios**:

1. **Given** a fixture repository whose manifest declares a landing branch that
   is not `main`, holding one spec with landed stories and one with none,
   **When** `list` runs, **Then** each row carries its landed count against its
   total, the two rows differ, and both counts are the ones read against the
   declared branch — proven by a committed test over two branches holding
   different landings, so a `main` default returns different numbers and fails,
   and asserting the frontmatter corpus is read once, so the state column and
   the count column cannot come from two walks that disagree.
2. **Given** a fixture corpus holding at least one `ready` spec and at least one
   `draft` spec, **When** `list` runs with `--state ready`, **Then** the ready
   spec's directory name is in the output, the draft spec's directory name is
   absent from it, and the number of spec rows equals the number of ready specs
   — proven by a committed test asserting all three. The positive half is
   load-bearing: an implementation that always emits no spec row satisfies the
   absence, and satisfies US3-S3 and US3-S5 as well, so the filter could ship as
   "always empty" and pass this whole story; and against a do-nothing production
   diff argparse refuses `--state` with `SystemExit(2)` and an empty stdout, so a
   test written to the absence alone is red for the wrong reason and green the
   moment the flag merely parses.
3. **Given** `--state` naming a state no spec is in, **When** `list` runs,
   **Then** the output holds no spec row and carries a line saying the filter
   matched nothing — proven by a committed test asserting both. A filter that
   silently falls back to unfiltered is worse than no filter.
4. **Given** no flags and a fixture corpus holding one blocked spec, **When**
   `list` runs, **Then** the render is still one line per spec — the line count
   equals the spec count — every row carries the new count column, and the
   blocked spec still names every one of its blockers on that same line —
   proven by a committed test asserting all three. This is the row invariant,
   not a frozen render: the count column is new, so the unflagged output is
   meant to differ from today's.
5. **Given** a fixture corpus that no git repository holds, **When** `list`
   runs, **Then** every row still renders, its count column reads `unknown`
   rather than a number, and the output says once that landings could not be
   read — proven by a committed test asserting every row's count column is the
   literal `unknown` and that the explanatory line is present. Zero and
   unreadable are different answers, and printing the first for the second tells
   an operator a landed spec has landed nothing.

## Functional Requirements

- **FR-001**: Every CLI verb that takes a spec directory — `spec validate`,
  `spec derive`, `spec landed` and `build ship` — MUST accept a spec number in
  place of a path.
- **FR-002**: A number MUST resolve by integer equality on the leading numeric
  segment of a direct child directory of the specs root, so leading zeros are
  optional and no prefix ever matches. It MUST use the same segment rule the
  writer half already applies at
  `factory/cli/nouns/spec.py:302` — `_pick_spec_number`.
- **FR-003**: A value that matches more than one directory MUST be refused,
  naming every candidate. That state is reachable only from a corpus in which
  two directories claim one number.
- **FR-004**: A value that matches no directory MUST be refused, naming the
  value and the specs root searched.
- **FR-005**: An argument that already names an existing directory MUST be used
  as that directory unchanged, with no resolution attempted, whatever it looks
  like and wherever it sits.
- **FR-006**: Resolution MUST honour `--specs-root` on the verbs that register
  it — `spec validate`, `spec derive` and `build ship` — and MUST fall back to
  the default root on `spec landed`, which registers none.
- **FR-007**: `ergane spec show` MUST report, for one spec — named by its
  number or by its directory, resolved through the resolver FR-002 requires —
  state, story count, landed count, task count, and blockers.
- **FR-008**: `show` MUST read landed facts against the declared landing branch
  — the explicit flag, then the manifest declaration, then `main` — and MUST
  take that read **without fetching**, calling
  `factory/workgraph/landed.py:130` — `landed_facts` with `fetch=False` and
  saying on its own output that the answer was read without fetching. It MUST
  NOT route the read through `factory/workgraph/cli.py:168` — `landed_command`,
  which is a printing command and keeps the fetching default. `show` MUST
  register `--default-branch` with a `None` default, so that first arm exists to
  be read and the manifest declaration can still win. That read MUST live in one
  **named reader** — a callable taking a spec directory and returning its landed
  facts, caching one scan per spec — rather than inline in `show`'s body,
  because FR-011 requires `list` to reuse that same object and forbids a second
  landed implementation.
- **FR-009**: `show` MUST degrade when no control plane is reachable, reporting
  the epic state as unknown rather than failing, and MUST reach the control
  plane through the guards `factory/cli/status.py` already declares rather than
  a blanket `except Exception`.
- **FR-010**: `show` MUST offer `--json`, the document MUST carry six facts —
  the five of FR-007 plus the epic state of FR-015 — under stable keys, and the
  human render MUST be produced from the same object the document serialises.
- **FR-011**: `ergane spec list` MUST carry a landed-versus-total count per row.
  The total MUST be the stories the spec declares, parsed the way
  `factory/cli/status.py:491` — `_declared_story_keys` parses them. The landed
  half MUST come from the reader US2 builds for FR-008 — one cached
  `factory/workgraph/landed.py:130` — `landed_facts` scan per spec, taken with
  `fetch=False`, against the branch that
  `factory/cli/status.py:378` — `_readiness_basis` resolves for the repository
  holding the corpus, never `main` by default. There MUST NOT be a second landed
  implementation.
- **FR-012**: `list` MUST accept a state filter, and MUST emit no spec row and a
  line saying so when the filter matches nothing.
- **FR-013**: Resolution MUST yield the real directory, so
  `epic_id = spec_dir.resolve().name` still names the full slug at every site
  that computes it — `factory/cli/nouns/spec.py:498` — `_validate_command`,
  `factory/workgraph/cli.py:314` — `derive_command`,
  `factory/workgraph/cli.py:182` — `landed_command` and
  `factory/cli/nouns/build.py:1035` — `ship_command`.
- **FR-014**: Resolution MUST NOT rebind `args.specs_root`. The comparison at
  `factory/workgraph/cli.py:332` — `derive_command` tests that value against the
  default string to decide whether the compiled graph's `specs_root` is the
  spec's own parent, and rewriting it changes what path callers compile.
- **FR-015**: `show` MUST report the epic state as a sixth fact, read through
  the `epic_status` query on the handle that
  `factory/workgraph/cli.py:160` — `workflow_id` names, the way
  `factory/cli/nouns/build.py:1119` — `_query_status` already asks it, and MUST
  report it as `unknown` when no control plane answered.
- **FR-016**: When no git repository holds the corpus, or the landing branch
  cannot be resolved, `list` MUST render every row's landed half as `unknown`
  and say once that landings could not be read — never `0` and never a failure.
  `factory/cli/status.py:378` — `_readiness_basis` is the written precedent: it
  degrades to attestation and labels the degrade on its own output.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-013, FR-014]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-007, FR-008, FR-009, FR-010, FR-015]
US3:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-011, FR-012, FR-016]
```

A chain of two merge edges, both declared rather than left inferred (069-US2
FR-007). US2 gates on US1 having **merged** because `show` takes a number and
there is no point building a verb against an argument form that does not exist
yet; US3 gates on US2 because FR-011 requires US3 to read landed facts through
the reader US2 builds — a second implementation is forbidden, so the reader has
to exist first — and because both add a column to operator-facing output and
both edit the corpus renderer, and three stories editing one CLI surface
concurrently is the collision shape that passes every branch check and fails in
the merge group. `depends_on` unlocks on verification and `depends_on_merged` on
merge (`factory/workgraph/derive.py:604` — `_check_edges`); these are merge
edges on purpose, and the cost is that this epic runs one node at a time.
