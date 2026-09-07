---
state: ready
fixes:
  - feedback/pr-8-spec-validate-has-no-library-form-and-its-composition-is-the-policy
# DRAFTED 2026-09-03 by the operator session, against ergane-buildout at 238b494.
# Every `file:line` in spec.md and plan.md was read from that commit and verified
# to resolve to the symbol named, not recalled.
#
# WHERE THIS CAME FROM. PR-8 of the `ergane-web` consolidated hand-over. A
# consumer whose own constitution forbids it to shell the CLI needs the verdict
# `ergane spec validate` produces, and cannot have it. That consumer today renders
# each checker's answer separately WITH AN ON-SCREEN BANNER STATING THAT THE CLI'S
# VERDICT IS NOT AVAILABLE TO IT. That banner is the honest rendering of a gap,
# and it stops being true the day this lands.
#
# THE MEASUREMENT IN THE DOCUMENT IS STALE AND THE PROBLEM HAS GROWN SINCE.
# PR-8 counted six layers, five of them individually exported and typed — which is
# what made it "a trap rather than a gap: a consumer can reach every part and not
# the whole". At HEAD there are ELEVEN layers and the five added since the wheel
# was cut are implemented as private functions INSIDE the CLI module. So a
# consumer re-composing the five exported pieces now silently under-reports the
# fixes-ledger, stale-anchor, symbol-anchor and judge-evidence refusals entirely.
# The drift PR-8 predicted has already happened, and the workaround it warned
# against is no longer merely fragile — it is unreachable.
#
# THIS IS A MOVE, NOT A REDESIGN. Every refusal message, every severity, the order
# the layers run in, and the `information` channel's deliberate non-effect on the
# exit code all stay exactly as they are. A changed message is a regression here,
# not an improvement: `ergane spec validate` is a verb operators read closely and
# 072's own lesson is that its precise refusals are load-bearing.
#
# WHY THE COMPOSITION IS THE DELIVERABLE. Which checks run, in what order, which
# failures are refusals and which are warnings — that IS the policy. Re-composing
# it in a consumer produces a verdict that agrees with the CLI on the day it is
# written and drifts the first time a severity changes. And the consumer wins that
# disagreement in practice, because the consumer is the thing on screen.
#
# NOT IN SCOPE. This spec does not add a layer, does not change the sentinel gate
# in `_derive_command`, and does not touch `spec new`, `spec derive` or
# `spec landed`.
#
# REFINED 2026-09-04 by the refinement workflow (refinement-2026-09-04); every
# anchor in spec.md, plan.md and tasks.md re-read from ergane-buildout at 602a92c.
#
# THE COUNT IN THE PARAGRAPH ABOVE IS WRONG AND THE BODY NOW CARRIES THE MEASURED
# ONE. `_validate_command`'s own numbered comments run 1 to 11 with `6.` used
# twice, and the draft counted the comments. The `checked` list a run actually
# emits holds TWELVE names. Ten of the twelve are implemented inside the CLI
# module — nine private functions and one, `slice_contention`, that is not a
# function at all but six inline lines of `_validate_command`. An implementer told
# "move five, compose eleven" leaves two layers behind and never notices.
#
# THE STORY THAT COULD NOT HAVE LANDED. US2 as drafted moved five private
# implementations in one diff. Measured at 602a92c those bodies are 36.2 KB of
# source; a move is a delete plus an add, so the assembled diff is about 72 KB
# against a 65,536-byte deterministic refusal — `DIFF_REFUSAL_THRESHOLD` at
# `factory/verify/diffbounds.py:66`, which is defined as, and today equals, the
# judge's input allowance `DIFF_INPUT_LIMIT` at
# `factory/verify/diffbounds.py:47` — before a single test line. The move is
# now three
# relocation stories — US2, and the new US5 and US6 — sized off measured bytes,
# and US3 does the composition and the rendering as one edit because they are one
# edit. Landed numbers are immutable; nothing was renumbered.
#
# THE BYTE-IDENTICAL CLAIM WAS NOT PROVABLE FROM A DIFF. "Stdout is identical to
# today's" names a tree the judge cannot see (Principle VIII, D-037). US1 now
# commits the golden capture FIRST, before any implementation moves, against a
# synthetic fixture trio rather than a live corpus spec — a corpus spec is refined
# weekly and would take the golden with it. Every later story asserts against that
# committed artifact.
#
# THE KEY IS KEPT, WHOLE. One key, and its ledger row asks for exactly
# `factory.spec.validate_spec(spec_dir, *, target_repo, specs_root) -> SpecValidation`
# with the verb a renderer over it; FR-001 through FR-009 answer it end to end and
# FR-010 through FR-014 are the sizing and the proof. Nothing was removed. That
# row's own `refs` (`factory/cli/nouns/spec.py:231` and `:388`) are stale 0.2.0
# line numbers — correcting them is a ledger act for the operator, not this spec.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): an adversarial review refuted the
# refined trio on three blocking defects and six minor ones. What changed: the
# US5/US6 boundary moved from a line that cut the judge-evidence family in half;
# the four module-level names the moved bodies depend on are now declared, and the
# finding type's relocation is mandatory rather than optional, because leaving
# them behind is an unimportable module and not a style question; one fixture trio
# became two, because a trio carrying a refusal never prints the all-pass sentence
# the golden exists to freeze; the three byte-for-byte scenarios were reworded to
# what their own diff carries; `_check_fixes` has four early returns, not three;
# `_check_evidence` does return a report; the relocation tasks now name symbols as
# well as line ranges; and the stale compiled artifact beside this file is now
# named. No FR was removed, no story renumbered, no key touched.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): a second adversarial review refuted
# the trio on the streams and on trap 3. THE GOLDEN CAPTURE IS SIX ARTIFACTS, NOT
# FOUR. Refusal and advisory lines, skipped-layer lines, information notes and the
# trailing sentinel count all print to STDERR (`factory/cli/nouns/spec.py:710`,
# `:733`, `:739`, `:747`); only the all-pass sentence, the judge-evidence report
# and the `--json` document reach stdout. A stdout-only golden froze none of the
# four rendered prefixes trap 9 forbids changing — and US3 is the story that
# rewrites them. The channel table now names the stream, FR-006 and FR-014 name
# three artifacts per trio, and plan trap 19 carries the mechanism and the command
# that reproduces it. TRAP 3's MECHANISM WAS FALSE: `_all_pass_phrases` reads
# `checked` for MEMBERSHIP only, never for order, so a tidied order changes the
# `--json` document and not one byte of the sentence; the trap, US3-S4 and T034
# now say so, and the controls are named as T034 plus FR-007's JSON golden. Also
# corrected: the clean trio's recipe skips `anchor_resolution` alone, not both
# anchor layers; three layers skip rather than refuse when their precondition is
# absent, which made US3-S2's five-way test vacuous (new trap 20); the `--json`
# key order and the deliberate absence of `judge_evidence` are load-bearing (new
# trap 21); `_check_evidence` appends its refusal rather than raising it; and US1
# is no longer asserted to be the smallest story. No FR was removed, no story
# renumbered, no key touched. The stale `workgraph.json` is still on disk — a
# refinement may not write or delete it — and the paragraph below, plan step 0 and
# T050 name the one command that clears it.
#
# WHAT IT COST, MEASURED. Nothing yet, and that is the point: the consumer's
# workaround is an on-screen banner saying the CLI's verdict is unavailable to it,
# filed at severity `info` with one occurrence and no incident behind it. What has
# already been paid is the drift the banner predicts — PR-8 measured six layers
# with five reachable; at 602a92c there are twelve with two reachable, so a
# consumer re-composing the exported pieces today under-reports the fixes-ledger,
# stale-anchor, symbol-anchor, judge-evidence and slice-contention answers
# entirely. The cost is the widening gap, not an outage already suffered, and
# re-grading the row is a ledger act for the operator rather than this spec.
#
# THE COMPILED ARTIFACT BESIDE THIS FILE IS STALE, AND MUST BE CLEARED BEFORE
# DISPATCH. `workgraph.json` in this directory was derived at 238b494 from the
# FOUR-story draft: its nodes are us1..us4 and its `us2.requirement_keys` are
# FR-003, FR-004 and FR-005. This file now declares SIX stories and fourteen
# requirements, and its US2 implements FR-010 — the anchor relocation — not the
# composition. `ergane build start` reads a compiled graph off disk at
# `factory/cli/nouns/build.py:808` — `start_command`, and those requirement keys
# travel through `factory/workgraph/workflow.py:1740` — `_run_node` and
# `factory/activities/verify_activities.py:187` — `snapshot_criteria` into
# `factory/verify/criteria.py:450` — `load_criteria`, which selects the criteria
# the judge scores, and through `factory/workgraph/prompt.py:606` —
# `_requirement_sections` into the prompt the node is handed. Dispatching this
# directory with `ergane build start` as it stands would build the four-node
# graph: the US2 node would be
# assembled and judged against the composition requirements while this spec's US2
# is the anchor relocation, US5, US6 and FR-010 through FR-014 would never be
# dispatched at all, and the operator would read four green nodes for a spec that
# is two-thirds unbuilt. The roadmap is not that route and does not read this
# artifact: `factory/roadmap/workflow.py:1170` — `_dispatch` re-derives the
# graph from spec.md through the `derive_spec` activity and never opens
# `workgraph.json`, so a schedule tick would build the six stories this file
# declares. The stale graph is `ergane build start`'s hazard alone, and the
# remedy below is the same either way.
# `ergane spec validate` re-reads spec.md and cannot see
# it. This refinement is not permitted to write or delete that artifact: the
# operator deletes it (it is untracked) or re-derives it and confirms the node
# list is us1, us2, us5, us6, us3, us4.
#
# NOT IN SCOPE, CORRECTED. The paragraph above says this spec "does not change the
# sentinel gate in `_derive_command`". That is true of the gate's BEHAVIOUR and
# false of its code, and an implementer meeting only the earlier sentence reads it
# as a prohibition on a move FR-011 requires. `factory/cli/nouns/spec.py:462` —
# `_scan_sentinels_in_trio` has two callers: the validate layer at
# `factory/cli/nouns/spec.py:638` and the derive gate at
# `factory/cli/nouns/spec.py:257`, inside `factory/cli/nouns/spec.py:255` —
# `_derive_command`. US5 moves that helper into `factory/spec/` and imports it
# back, so BOTH callers keep calling it and `_derive_command`'s refusal text is
# unchanged. Nothing else about `spec derive` is touched.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04): a third adversarial review
# refuted the trio on two blocking defects and five minor ones, all in US3 and
# US5 and all of the 'instruction gone wrong' class validate cannot see.
# `_validate_command` DOES NOT BUILD ONE FINDING IN ITS OWN BODY, IT BUILDS
# FIVE, and three of those are complete layer wrappers with their own
# skip-reason strings that no `_check_` function holds — so US3's scope, and
# T037's and T039's enumeration, were cut from a count of one. SIX IN-TREE TEST
# FILES REACH THE RELOCATED BODIES THROUGH THE CLI MODULE and only two of them
# were named: four reach the layer functions as attributes of
# `factory.cli.nouns.spec`, and two disable a layer by patching that module and
# then compare the corpus with and without it — controls that go silently
# vacuous the moment US3 makes the verb a renderer, because the composition
# then reads `factory.spec`'s globals and the patch lands on nothing. FR-011
# now names the four, FR-015 and US3-S8/US3-S9 own the two controls and the
# import seam, and plan traps 22 and 23 carry both mechanisms. Also corrected:
# the refusal constant is `DIFF_REFUSAL_THRESHOLD`, not the attention allowance
# it defaults to; the finding built for a failed derivation carries the layer
# name `workgraph` while `checked` carries `workgraph_derivation`, and the
# sentinel finding carries `sentinel` while `checked` carries `sentinels` —
# two rendered-string mismatches a typed report would normalise away; US2-S1
# was missing `_SYMBOL_ANCHOR_RE` and `_DISPATCHABLE_STATES`, both inside the
# span it moves; nine symbol-form anchors were line-wrapped and therefore
# invisible to the tier that would catch them drifting; US3's size is
# re-estimated with a number to stop at; and the roadmap's dispatch route is
# distinguished from `build start`'s above. No FR was removed, no story
# renumbered, no key touched, and the stale `workgraph.json` is still on disk
# for the operator to clear.
---

# Feature Specification: spec validate has one implementation and two faces

**Created**: 2026-09-03
**Depends on**: nothing.

## The gap, stated precisely

1. `ergane spec validate` composes **twelve** layers into one verdict. The list
   it reports them under is seeded with four names at
   `factory/cli/nouns/spec.py:504` and appended to at eight further points, and a
   clean run over this spec emits exactly twelve: `frontmatter`,
   `workgraph_derivation`, `persona_registry`, `scenario_coverage`, `fixes`,
   `prompt_assembly`, `slice_coverage`, `slice_contention`, `sentinels`,
   `anchor_resolution`, `symbol_anchors`, `evidence`.
2. All of that composition lives inside one function that takes an
   `argparse.Namespace`, prints, and returns an exit code:
   `factory/cli/nouns/spec.py:490` — `_validate_command`.
3. The report is a plain dict assembled inline at
   `factory/cli/nouns/spec.py:677` and consumed twenty lines later, where an
   `as_json` branch at `factory/cli/nouns/spec.py:698` prints it with
   `json.dumps` at `factory/cli/nouns/spec.py:699` and moves on. Nothing returns
   it. The verdict itself is computed and discarded at
   `factory/cli/nouns/spec.py:750`.
4. Findings carry a private, non-dataclass type:
   `factory/cli/nouns/spec.py:483` — `_ValidateFinding`.
5. There is no `factory/spec/` package. `ls factory/spec` errors.

**The one public name is a decoy.**
`factory/cli/nouns/spec.py:275` — `validate_spec_command` is a CLI wrapper
whose body delegates to
`_validate_command`, added so `build ship` could stream the same stdout
(`factory/cli/nouns/build.py:1039`). Namespace in, print out, exit code back.
`grep -rn "validate_spec\|SpecValidation" factory/` returns exactly three hits:
that wrapper and its two call sites.

**Ten of the twelve layers are implemented inside the CLI module.** Nine are
private functions — `factory/cli/nouns/spec.py:999` — `_check_frontmatter`,
`factory/cli/nouns/spec.py:1231` — `_check_fixes`,
`factory/cli/nouns/spec.py:1304` — `_check_workgraph`,
`factory/cli/nouns/spec.py:1311` — `_check_personas`,
`factory/cli/nouns/spec.py:1379` — `_check_scenario_coverage`,
`factory/cli/nouns/spec.py:462` — `_scan_sentinels_in_trio`,
`factory/cli/nouns/spec.py:1023` — `_check_anchor_resolution`,
`factory/cli/nouns/spec.py:886` — `_check_symbol_anchors`, and
`factory/cli/nouns/spec.py:1781` — `_check_evidence`, which returns the private
`factory/cli/nouns/spec.py:1666` — `_JudgeEvidenceReport`. The tenth,
`slice_contention`, has no function at all: it is inline in `_validate_command`
at `factory/cli/nouns/spec.py:614-631`, at severity `advisory`
(`factory/cli/nouns/spec.py:617`). It is not the only advisory in the module —
`factory/cli/nouns/spec.py:1379` — `_check_scenario_coverage` grades its
uncovered-scenario finding `advisory` at `factory/cli/nouns/spec.py:1414`.

**And `slice_contention` is not the only thing `_validate_command` builds in
its own body: it constructs a finding at five sites, three of which are whole
layer wrappers.** They are the derivation refusal at
`factory/cli/nouns/spec.py:535` (layer `workgraph`, raised out of the
`try` at `factory/cli/nouns/spec.py:525-535`); the `prompt_assembly` wrapper at
`factory/cli/nouns/spec.py:557-574`, whose finding is built at
`factory/cli/nouns/spec.py:559` and whose `else` writes a skip-reason string no
checker holds; the `slice_coverage` wrapper at
`factory/cli/nouns/spec.py:582-604`, whose finding is built at
`factory/cli/nouns/spec.py:590` and which alone decides, on
`entry.informational`, whether an answer lands in `findings` or in
`information`; the `slice_contention` block above; and the `sentinels` wrapper
at `factory/cli/nouns/spec.py:638-645`, whose finding is built at
`factory/cli/nouns/spec.py:640`. Three complete layers — their names, their
severities, their skip reasons and the `information` routing — exist only as
lines of the CLI command, which is why a sweep that moves `def _check_`
functions and the one contention block leaves a quarter of the policy behind.

**Two of the twelve layer names differ between the finding and the `checked`
entry, and both spellings are rendered.** A failed derivation builds its
finding with the layer `workgraph` (`factory/cli/nouns/spec.py:535`, and again
in `factory/cli/nouns/spec.py:1304` — `_check_workgraph` at
`factory/cli/nouns/spec.py:1308`) while `checked` is seeded with
`workgraph_derivation` at `factory/cli/nouns/spec.py:506`; a sentinel note
carries the layer `sentinel` (`factory/cli/nouns/spec.py:640`) while `checked`
gains `sentinels` at `factory/cli/nouns/spec.py:645`. Both pairs reach the
operator — the first through the `[layer]` prefix and the `--json`
`findings[].layer` key, the second through the same two places — so a typed
report that normalises either pair into one name changes rendered output on
the first spec that trips it.

Only two layers have an exported checker a consumer can call as it stands —
`check_prompt_assembly` and `check_slice_coverage`, imported at
`factory/cli/nouns/spec.py:60` — and even there what is exported is the answer,
not the layer: the finding's name and severity, the `checked` append and the
skip-reason string for both are written inline in `_validate_command`, at
`factory/cli/nouns/spec.py:557-574` and `factory/cli/nouns/spec.py:582-604`.
The rest of what is exported are *primitives*
(`derive_workgraph`, `validate_workgraph`, `load_personas`, `parse_spec`,
`scan_sentinels`); the layer around each primitive — its name, its severity, its
skip reason — is private. That is the drift PR-8 predicted, and it has already
happened: a consumer re-composing the exported pieces omits the fixes-ledger,
stale-anchor, symbol-anchor, judge-evidence and slice-contention answers
entirely.

**And even in-tree callers reach it by argv.**
`factory/cli/install.py:1078` — `_spec_validate_argv` builds
`["spec", "validate", ...]` and
`factory/cli/install.py:1028` runs it back through the CLI entry point from
inside the package. If a library form existed, that path would be its first
consumer.

**Five module-level names sit outside every layer body and are read from inside
three of them.** The finding type
`factory/cli/nouns/spec.py:483` — `_ValidateFinding` is constructed by every
relocated family; the anchor grammars
`_ANCHOR_RE` at `factory/cli/nouns/spec.py:68` and `_BARE_LINE_RE` at
`factory/cli/nouns/spec.py:71` are read only from inside `_check_anchor_resolution`
(at `factory/cli/nouns/spec.py:1123` and `factory/cli/nouns/spec.py:1092`); the
scenario-id grammar `_SCENARIO_ID_RE` at `factory/cli/nouns/spec.py:65` is read
only at `factory/cli/nouns/spec.py:1407` inside `_check_scenario_coverage`; and
`factory/cli/nouns/spec.py:79` — `_vacuous_registry`, with the constant
`_STRUCTURAL_TIMEOUT_S` at `factory/cli/nouns/spec.py:76` that it reads, is called
only at `factory/cli/nouns/spec.py:1306` inside `_check_workgraph`. They are the
reason the relocation is a move of families rather than of functions.

## The rule this spec is asking for

**One implementation of the validation policy, exported and typed, with the CLI
verb as a renderer over it — so the two forms cannot disagree.**

The policy the typed report has to carry whole is the four-way channel split
below, all of which is decided inside `_validate_command` today. A report type
that cannot express every row reintroduces the drift it exists to end.

| Channel | Held in | Moves the exit code | Rendered as | On |
| --- | --- | --- | --- | --- |
| refusal | `findings`, severity `refusal` | yes — `EXIT_USER` (`factory/cli/nouns/spec.py:750`) | `ergane spec validate — refusal: [layer] …` | stderr (`factory/cli/nouns/spec.py:710`) |
| advisory | `findings`, severity `advisory` | no — the all-pass sentence is printed with `see advisory above` | `ergane spec validate — advisory: [layer] …` | stderr (`factory/cli/nouns/spec.py:710`) |
| information | the separate `information` list | no, by construction | `ergane spec validate — noted, not a refusal: [layer] …` | stderr (`factory/cli/nouns/spec.py:739`) |
| skipped | `skipped`, with a reason string | no | `ergane spec validate — layer 'X' not checked: …` | stderr (`factory/cli/nouns/spec.py:733`) |

**Three of the four channels print to the diagnostic stream, and the golden
capture has to follow them there.** Exactly three writes reach stdout: the
all-pass sentence (`factory/cli/nouns/spec.py:714` and
`factory/cli/nouns/spec.py:718`), the judge-evidence report lines
(`factory/cli/nouns/spec.py:725`), and the `--json` document
(`factory/cli/nouns/spec.py:699`). The four rendered prefixes in the table above
— the strings this spec forbids itself to change — are printed to stderr and
nowhere else, and the trailing ERGANE-TODO count
(`factory/cli/nouns/spec.py:747`) with them. That is why FR-014 freezes **three**
artifacts per trio rather than one, and why a stdout-only capture would have left
US3 free to rewrite every prefix with nothing to fail against.

The table is also why the golden capture needs two fixture trios rather than one.
A run carrying a refusal returns `EXIT_USER`, and the two branches at
`factory/cli/nouns/spec.py:712` and `factory/cli/nouns/spec.py:717` that render
the all-pass sentence are never taken — so a single trio carrying a refusal
freezes every shape except the one sentence a change in which layers reach
`checked` would silently rewrite.

### What this spec is not

It is not a redesign. No message changes, no severity changes, no reordering. A
golden capture committed before anything moves, and a test driving both forms
over the whole corpus, exist precisely so that "nothing changed" is provable
rather than asserted.

It is not a new layer. Twelve go in and twelve come out.

It is not a widening of the CLI's surface. `spec validate` keeps its flags, its
output and its exit codes.

It is not a redesign of the checkers' signatures. They accumulate into
caller-owned `findings`, `skipped` and `checked` lists today, and they still do
after they move — with one exception that must survive the move intact:
`factory/cli/nouns/spec.py:1781` — `_check_evidence` accumulates into those lists
*and* returns `_JudgeEvidenceReport`, which the verb consumes at
`factory/cli/nouns/spec.py:675`, prints at `factory/cli/nouns/spec.py:724` and
serialises under the `judge_evidence` key at `factory/cli/nouns/spec.py:693`.
Only `validate_spec` learns to build a typed report from those lists. Changing
the signatures while relocating is what turns a mechanical move into a diff no
story can carry.

## User Scenarios & Testing

Stories are presented in the order they must land. US5 and US6 were split out of
the drafted US2 on measured bytes, so they take new numbers and nothing is
renumbered.

### User Story 1 - A typed report exists, and today's output is captured (Priority: P1)

As a consumer, there is a type I can hold that describes a validation; and before
one line of policy moves, what the verb prints today is committed where a later
diff can be checked against it.

**Why this priority**: P1 and it depends on nothing. Every later story returns,
renders or asserts against what this story adds. The golden capture in particular
cannot be taken after the fact, and a criterion saying "identical to today's
output" is undecidable by a judge that sees only the diff — so today's output has
to become an artifact in the diff. This story also owns the shared floor: the
finding type every relocated body constructs has to be in `factory/spec/` before
the first body moves, or the first relocation cannot compile.

**Independent Test**: Import the type and construct a report; assert its fields.
Run the verb over each committed fixture trio and compare with its committed
capture.

**Acceptance Scenarios**:

1. **Given** the `factory.spec` package, **When** it is imported, **Then** the
   diff adds a test asserting it exports `SpecValidation` and a finding type
   carrying a layer name, a severity and a message, plus an overall verdict.
2. **Given** that type, **When** a report is built, **Then** a committed test
   asserts it holds all four channels of the table above as separate members —
   refusals, advisories, information notes, and skipped layers each with their
   reason string.
3. **Given** a report carrying only information entries and no refusal,
   **When** its verdict is read, **Then** a committed test asserts the verdict is
   a pass, preserving that channel's deliberate non-effect on the exit code.
4. **Given** the finding type, **When** it is constructed with a layer and a
   message alone, **Then** a committed test asserts its severity defaults to
   `refusal` and that `advisory` is accepted — the same constructor shape
   `_ValidateFinding` has today, so a relocated checker needs no signature edit.
5. **Given** two synthetic fixture trios committed under `tests/`, each in its
   own parent directory and neither a spec from `specs/` — one that validates
   clean and one deliberately defective — **When** the verb is run over each
   before any implementation moves, **Then** the diff adds six golden artifacts,
   each trio's stdout, its stderr and its `--json` document, with the repository
   root normalised out; the clean trio's stdout artifact carries the all-pass
   sentence and its stderr artifact carries an information note and a
   skipped-layer line, and the defective trio's stderr artifact carries a refusal
   line and an advisory line while its stdout artifact carries the judge-evidence
   report and no all-pass sentence.
6. **Given** `factory/cli/nouns/spec.py`, **When** the diff is read, **Then** it
   no longer defines `_ValidateFinding` and binds the finding type imported from
   `factory.spec` under that same local name, so no construction site in the
   module changes — proven by a committed test that reads the module source for
   the class statement and asserts the bound object's `__module__` is under
   `factory.spec`.

### User Story 2 - The anchor and symbol layers leave the CLI module (Priority: P2)

As a maintainer, the two layers 072 added stop being private to a CLI module.

**Why this priority**: P2 and it follows US1. It is the first relocation and it
is the largest — `_check_anchor_resolution` alone is 9.8 KB of source — so it
sets the pattern the next two follow, and it is sized to land alone.

**Independent Test**: Import the moved checkers from `factory.spec`; run the verb
over both fixture trios and diff against US1's golden captures.

**Acceptance Scenarios**:

1. **Given** the anchor family, **When** the diff is read, **Then**
   `factory/cli/nouns/spec.py` no longer defines `_check_anchor_resolution`,
   `_check_symbol_anchors`, `_symbol_spans`, `_line_hits_symbol`,
   `_read_citation_files`, `_spec_state`, `_severity_for_state`,
   `_SYMBOL_ANCHOR_RE`, `_DISPATCHABLE_STATES`, `_ANCHOR_RE` or `_BARE_LINE_RE`,
   and imports them from `factory.spec` instead. `_SYMBOL_ANCHOR_RE`
   (`factory/cli/nouns/spec.py:795`) and `_DISPATCHABLE_STATES`
   (`factory/cli/nouns/spec.py:800`) sit inside the span this story moves and
   are read only by the checkers in it; `_ANCHOR_RE` and `_BARE_LINE_RE` sit
   above it and are read only from inside the moved checker. Leaving any of the
   four behind makes the moved body reach back into the CLI module.
2. **Given** the moved functions, **When** their bodies are read in the diff,
   **Then** every refusal string and every parameter is unchanged, and they still
   append into caller-owned `findings`, `skipped` and `checked` lists rather than
   returning a report.
3. **Given** the fixture trios from US1, **When** the verb is run over each,
   **Then** the diff carries, as pasted committed evidence, the comparison of
   this story's stdout, its stderr and its `--json` output against US1's six
   golden artifacts, and it is empty on all three streams; the committed golden
   test US1 added is named by path in the task as the standing guard that keeps
   it empty.
4. **Given** the CLI module, **When** a committed test inspects it, **Then** the
   anchor checkers it calls are asserted to be the objects defined in
   `factory.spec`, not re-declarations.

### User Story 5 - The frontmatter, ledger, graph, persona, scenario and sentinel layers leave the CLI module (Priority: P2)

As a maintainer, the six remaining non-evidence layer bodies stop being private to
a CLI module.

**Why this priority**: P2 and it follows US2. Split from the drafted US2 on
measured bytes: the three relocation families together are 45.4 KB of source, and
a move is a delete plus an add.

**Independent Test**: Import the moved checkers from `factory.spec`; run the verb
over both fixture trios and diff against US1's golden captures.

**Acceptance Scenarios**:

1. **Given** this family, **When** the diff is read, **Then**
   `factory/cli/nouns/spec.py` no longer defines `_check_frontmatter`,
   `_check_fixes`, `_check_workgraph`, `_check_personas`, `_candidate_graph`,
   `_check_scenario_coverage`, `_scan_sentinels_in_trio`, `_tasks_text`,
   `_SCENARIO_ID_RE`, `_vacuous_registry` or `_STRUCTURAL_TIMEOUT_S`, and imports
   them from `factory.spec` instead. The last three are module-level names read
   only from inside the moved bodies, and `_STRUCTURAL_TIMEOUT_S` is read only by
   `_vacuous_registry`.
2. **Given** `_check_fixes`, **When** its moved body is read in the diff,
   **Then** its four early returns are asserted intact by a committed test: an
   unreadable `spec.md` returns silently and adds nothing to any list, a spec
   with no `fixes:` key adds neither a `checked` nor a `skipped` entry, an absent
   store adds a `skipped` entry only, an unopenable store adds a different
   `skipped` entry only, and only the success path appends `fixes` to `checked`.
3. **Given** the fixture trios from US1, **When** the verb is run over each,
   **Then** the diff carries, as pasted committed evidence, the comparison of
   this story's stdout, its stderr and its `--json` output against US1's six
   golden artifacts, and it is empty on all three streams; the committed golden
   test US1 added is named by path in the task as the standing guard that keeps
   it empty.
4. **Given** the moved bodies, **When** they are read in the diff, **Then** every
   refusal string and every parameter is unchanged, including
   `_check_fixes`'s call to `resolve_factory_root()`.
5. **Given** the five in-tree tests that reach this family through the CLI
   module, **When** the diff is read, **Then** `tests/test_062_us3_skills.py`
   (`_vacuous_registry`), `tests/test_slice_coverage.py` and
   `tests/test_prompt_assembly.py` (`_check_frontmatter`, `_check_workgraph`,
   `_check_personas`, `_check_scenario_coverage`),
   `tests/test_122_findings_store_isolation.py` (`_check_fixes`, imported at
   module scope) and `tests/test_us1_registry_resolution.py` (`_check_personas`)
   each reach the moved bodies at their new home rather than as attributes of
   `factory.cli.nouns.spec`, and every assertion each of them makes is asserted
   still present rather than deleted or served by a shim.

### User Story 6 - The judge-evidence layer leaves the CLI module (Priority: P2)

As a maintainer, the layer 102 added — and the report type it returns — stop being
private to a CLI module.

**Why this priority**: P2 and it follows US5. It is separated because it carries
its own object graph: a checker, a report dataclass, its helpers and the closed
marker vocabulary they read, 18.4 KB of source, which is a 37 KB diff on its own.

**Independent Test**: Import `_check_evidence`'s successor and its report type
from `factory.spec`; run the verb over both fixture trios and diff against US1's
golden captures.

**Acceptance Scenarios**:

1. **Given** the evidence family, **When** the diff is read, **Then**
   `factory/cli/nouns/spec.py` no longer defines `_check_evidence`,
   `_JudgeEvidenceReport`, `_StoryCriteria`, `_BorderlineClause`,
   `_Declarations`, `_then_clauses`, `_runtime_markers`, `_names_a_declared_gate`,
   `_manifest_declares_no_gates`, `_declared_gates`, `_evidence_refusal`,
   `_borderline_warning`, `_story_criteria`, `_RUNTIME_MARKERS`,
   `_DIFF_EVIDENCE_RE` or `_PROVABLE_EXAMPLE`, and imports them from
   `factory.spec` instead. `_RUNTIME_MARKERS` is the marker vocabulary
   `_runtime_markers` reads and it must travel with it.
2. **Given** the moved report type, **When** the diff is read, **Then** a
   committed test asserts its `as_dict()` and its `lines()` output are unchanged,
   because the verb prints one and serialises the other, and that the moved
   checker still returns it as well as appending to the caller-owned lists.
3. **Given** the fixture trios from US1, **When** the verb is run over each,
   **Then** the diff carries, as pasted committed evidence, the comparison of
   this story's stdout, its stderr and its `--json` output against US1's six
   golden artifacts, and it is empty on all three streams; the committed golden
   test US1 added is named by path in the task as the standing guard that keeps
   it empty.
4. **Given** a spec whose only defect is an unevidenceable Then-clause,
   **When** the moved checker is called directly, **Then** a committed test
   asserts the refusal it **appends to the caller-owned `findings` list** — it
   appends, it does not raise — is the same string the verb rendered before the
   move, taken from US1's golden capture of the defective trio's **stderr**,
   which is the stream every refusal line is printed on.

### User Story 3 - The verb is a renderer over one composition (Priority: P3)

As an operator, the verb prints exactly what it printed before, and every layer
now reaches it through the library.

**Why this priority**: P3 and it follows US6. Composition and rendering are one
edit to one function, so they are one story; splitting them would mean two
rewrites of the same region and the merge-group collision the chain exists to
avoid. It comes last of the code stories because it is the one with output
regression risk, and by now every body it composes is already where it belongs.

**Independent Test**: From a Python session, call `validate_spec` for one spec
directory and read the returned report; run the verb over both fixture trios and
diff against US1's golden captures.

**Acceptance Scenarios**:

1. **Given** a spec directory, **When** `validate_spec` is called with a target
   repo and a specs root, **Then** a committed test asserts it returns the typed
   report with no `argparse.Namespace` constructed and no stdout captured.
2. **Given** the library form, **When** a committed test drives it over specs
   defective in each of the five ways a re-composing consumer misses today — a
   stale line anchor, a symbol anchor, an unresolvable `fixes:` key, a missing
   judge evidence answer and a slice contention — **Then** each is asserted
   present in the returned report, the contention one at severity `advisory`.
3. **Given** the twelve layers, **When** a committed test reads the report,
   **Then** the `checked` sequence it carries is asserted equal to the seeded-then-
   appended order the verb emits today — `frontmatter`, `workgraph_derivation`,
   `persona_registry`, `scenario_coverage`, `fixes`, … — which is not the order
   the layers run in, and must not be tidied into it.
4. **Given** the fixture trios from US1, **When** the verb is run over each,
   **Then** a committed test asserts its stdout and its stderr each equal that
   trio's golden artifact for that stream byte for byte and its exit code is
   unchanged — the clean trio's stdout for the all-pass sentence, and both trios'
   stderr for the four rendered prefixes this story's rewrite of the renderer
   would otherwise change unobserved.
5. **Given** `--json`, **When** the verb runs over each fixture trio, **Then**
   the diff shows the document serialised from the typed report rather than from
   an inline dict, and a committed test asserts it equals that trio's golden JSON
   artifact byte for byte.
6. **Given** the CLI module, **When** the diff is read, **Then** it composes no
   layer itself — including the `slice_contention` block that is six inline lines
   of `_validate_command` today — and a committed test asserts it holds no
   finding construction of its own.
7. **Given** `factory/cli/install.py`, **When** the diff is read, **Then** its
   demonstration stage calls the library form instead of building an argv list,
   and a committed test asserts the lines the demonstration prints are unchanged.
8. **Given** the two in-tree corpus controls that disable a layer by rebinding
   it on `factory.cli.nouns.spec` and then compare the whole corpus with and
   without it —
   `tests/test_089_validate_checks_fixes.py:300` — `_validate_without_fixes_layer`
   and
   `tests/test_102_unprovable_criteria.py:425` — `_validate_without_evidence_layer`
   — **When** the verb becomes a renderer,
   **Then** the diff re-points both at the module the composition actually
   reads, and a committed test asserts that for a spec the layer refuses the
   disabled run and the enabled run return **different** findings — so a
   control that has stopped disabling anything fails instead of passing.
9. **Given** the CLI module composing no layer, **When** the diff is read,
   **Then** it no longer imports the relocated layer functions at all, and a
   committed test asserts no file under `tests/` reaches one of them as an
   attribute of `factory.cli.nouns.spec` — the four US5 re-pointed and the two
   controls above included.

### User Story 4 - The two forms agree, provably (Priority: P4)

As a maintainer, the CLI and the library cannot disagree without a red test.

**Why this priority**: P4 and it follows US3. PR-8 called this "the cheapest way
to guarantee the two never disagree", and it is nearly free: the corpus is on
disk.

**Independent Test**: Drive both forms over every spec in `specs/` and compare.

**Acceptance Scenarios**:

1. **Given** every spec directory in this repository's `specs/`, **When** both
   the library form and the CLI verb are driven over each, **Then** a committed
   test asserts they return the same verdict for every spec.
2. **Given** the same corpus, **When** the two are compared, **Then** the
   committed test asserts they agree on the per-layer findings and severities,
   not merely on the overall pass or fail.
3. **Given** a spec added to the corpus later, **When** the suite runs, **Then**
   the committed test is asserted to enumerate `specs/` by globbing at call time
   rather than by a literal list, so the guarantee does not decay as specs are
   minted.
4. **Given** the corpus test, **When** the diff is read, **Then** it drives the
   CLI face in-process through the CLI entry point with stdout captured, not by
   spawning a subprocess per spec, and the diff carries the pasted wall-clock
   line for the whole test.

## Functional Requirements

- **FR-001**: A `factory.spec` package MUST export `SpecValidation`, a typed
  validation report carrying per-layer findings with layer name, severity and
  message, and an overall verdict. The finding type MUST be defined in
  `factory/spec/`; `factory/cli/nouns/spec.py` MUST stop defining
  `_ValidateFinding` and MUST bind the imported type under that same local name,
  so no construction site in the CLI module changes and every later relocation
  has a finding type to construct that does not live in the module it is leaving.
- **FR-002**: The report MUST hold refusals, advisories, information notes and
  skipped layers with their reasons as separate members, and neither information
  notes nor skipped layers may affect the verdict.
- **FR-003**: `validate_spec(spec_dir, *, target_repo, specs_root)` MUST return
  that report without requiring an `argparse.Namespace` or stdout capture.
- **FR-004**: All twelve layers MUST be reachable through the library form,
  including `slice_contention`, which is inline in `_validate_command` today.
- **FR-005**: Layer run order, the order of the names in the emitted `checked`
  sequence, and every severity MUST be unchanged, including the advisory grade on
  slice contention.
- **FR-006**: `ergane spec validate`'s stdout **and its stderr** over each
  fixture trio MUST each equal that trio's golden artifact for that stream of
  FR-014 byte for byte, and its exit codes MUST be unchanged. Both streams are
  named because the four rendered refusal, advisory, skipped-layer and
  information prefixes are printed to stderr, so a stdout-only comparison would
  hold none of them.
- **FR-007**: `--json` MUST serialise the typed report rather than assembling a
  dict inline, and the emitted document over each fixture trio MUST equal that
  trio's golden JSON artifact of FR-014 byte for byte.
- **FR-008**: The CLI command MUST compose no layer itself and MUST construct no
  finding of its own, reaching all twelve through the library form.
- **FR-009**: A test MUST drive both forms over every spec in `specs/`, enumerated
  by globbing at call time, and assert they agree on the verdict and on the
  per-layer findings and severities; it MUST drive the CLI face in-process rather
  than by spawning a subprocess per spec.
- **FR-010**: The anchor and symbol layer bodies — `_check_anchor_resolution`,
  `_check_symbol_anchors`, `_symbol_spans`, `_line_hits_symbol`,
  `_read_citation_files`, `_spec_state`, `_severity_for_state` — together with the
  module-level regexes they alone read, `_ANCHOR_RE` and `_BARE_LINE_RE`, MUST be
  defined in `factory/spec/` and imported by the CLI module, with signatures and
  refusal strings unchanged.
- **FR-011**: The frontmatter, ledger, work-graph, persona, scenario-coverage,
  sentinel and tasks-text bodies, together with the module-level names they alone
  read — `_SCENARIO_ID_RE`, `_vacuous_registry` and the `_STRUCTURAL_TIMEOUT_S`
  constant it reads — MUST be defined in `factory/spec/` and imported by the CLI
  module, with signatures, early returns and refusal strings unchanged; and the
  five in-tree tests that reach these bodies as attributes of
  `factory.cli.nouns.spec` — `tests/test_062_us3_skills.py`,
  `tests/test_slice_coverage.py`, `tests/test_prompt_assembly.py`,
  `tests/test_122_findings_store_isolation.py` and
  `tests/test_us1_registry_resolution.py` — MUST be updated to the new home
  rather than deleted or served by a shim left in the CLI module.
- **FR-012**: The judge-evidence checker, its report type, its helpers and the
  module-level constants they read — `_RUNTIME_MARKERS`, `_DIFF_EVIDENCE_RE` and
  `_PROVABLE_EXAMPLE` — MUST be defined in `factory/spec/` and imported by the CLI
  module, with `as_dict()` and `lines()` output unchanged and with the checker
  still returning its report to the caller.
- **FR-013**: `factory/cli/install.py`'s demonstration stage MUST obtain its
  validation through the library form rather than by building an argv list, and
  the lines the demonstration prints MUST be unchanged.
- **FR-014**: The repository MUST carry, committed before any layer body moves,
  golden captures of the verb's stdout, its stderr and its `--json` document —
  three artifacts per trio, six in all — over **two** fixture trios held under
  `tests/`, not specs from `specs/`, each in a parent directory holding nothing
  else: one that validates clean, whose stdout artifact carries the all-pass
  sentence and whose stderr artifact carries an information note and a
  skipped-layer line, and one deliberately defective, whose stderr artifact
  carries a refusal line and an advisory line. The repository root MUST be
  normalised out of every artifact.
- **FR-015**: The two in-tree corpus controls that disable a layer by rebinding
  it on `factory.cli.nouns.spec` MUST be re-pointed at the module the
  composition reads, and a committed test MUST assert that on a spec the layer
  refuses the disabled run and the enabled run return different findings, so
  neither control can pass while disabling nothing. Once the CLI composes no
  layer it MUST no longer import the relocated layer functions, and no test
  under `tests/` may reach one of them through it.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-014]
US2:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-010]
US5:
  depends_on: []
  depends_on_merged: [US2]
  implements: [FR-011]
US6:
  depends_on: []
  depends_on_merged: [US5]
  implements: [FR-012]
US3:
  depends_on: []
  depends_on_merged: [US6]
  implements: [FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-013, FR-015]
US4:
  depends_on: []
  depends_on_merged: [US3]
  implements: [FR-009]
```

A full chain, and it is honest rather than defensive: every story edits
`factory/cli/nouns/spec.py` — six of them delete from it and one rewrites its
largest function — and every story after the first adds to the same
`factory/spec/` package. Concurrent stories would produce conflicting rewrites of
the same 1,865-line module, the collision shape that passes every PR check and
fails in the merge group. Each edge is declared rather than left inferred
(069-US2 FR-007).

The chain also orders the risk correctly. US1 fixes the shape, moves the finding
type every later body constructs, and freezes today's output as an artifact, so
nothing after it has to argue from a tree the judge cannot see. US2, US5 and US6
are three mechanical relocations, split on measured bytes against the
65,536-byte diff refusal rather than on taste, each provable by the same golden
captures. US3 is the one behavioural edit, taken last, when every body it
composes already sits where it belongs. US4 is the standing proof that the two
faces cannot drift afterwards.
