---
state: draft
depends_on_landed: [134-a-gate-declares-the-artifact-it-writes-and-the-platform-carries-it]
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04-tail) from
# docs/triage-2026-09-03-ergane-web-round3.md § "the-judge-can-look-at-what-the-story-built"
# (lines 258-274), against ergane-buildout at 602a92c. Every `file:line` in spec.md
# and plan.md was read from that commit with `sed -n` and verified to resolve to the
# symbol named, not recalled.
#
# THIS SPEC MUST NOT BE FLIPPED READY BEFORE AN OPERATOR AMENDS PRINCIPLE VIII.
# Principle VIII is marked NON-NEGOTIABLE (`.specify/memory/constitution.md:63`, its
# evidence sentence at `.specify/memory/constitution.md:72-76`) and is anchored by
# D-050 (`.specify/memory/constitution.md:162`) and D-037
# (`.specify/memory/constitution.md:167`). It says the judge is given the story's
# diff and the criteria snapshot and nothing else. THAT SENTENCE IS ALREADY OUT OF
# STEP WITH THE TREE, AND THE AMENDMENT SHOULD SAY SO. Spec 116 landed on
# 2026-08-31 (`8f5f633`, `f0d2a14`, `6f4f0b1`) and put a third input on that path:
# the system prompt at `factory/verify/judge.py:138` already tells the judge "You
# may also be given this factory's gate results", `_gate_blocks` assembles them and
# `JudgeVerdict.gates_shown` records whether they were shown. Neither
# `.specify/memory/constitution.md` nor `docs/decisions.md` carries an amendment for
# it — the last constitutional amendment is D-051, 2026-08-24
# (`.specify/memory/constitution.md:157-160`), and the last decision is D-052. So a
# declared artifact is the FOURTH input, not the third, and the doctrine has been
# behind the code since 2026-08-31. An amendment drafted to admit only this spec's
# channel would leave that drift unrecorded and would have to be written again the
# next time the same thing happens. Amend the class instead: the judge is given the
# story's diff, the criteria snapshot, and the factory's own measurements of that
# same attempt — its gate results and the artifacts its gates declared — and nothing
# else. Record the 116 drift in the same `docs/decisions.md` entry.
# That amendment plus its `docs/decisions.md` entry are operator acts: an
# implementer who edits the constitution to make its own story coherent has changed
# what every future agent is held to. Nothing in the gate can check that the entry
# exists, which is why it is written here, in the one place the operator reads
# before flipping the flag. The trio is arranged so no production change requires
# the edit — the spec builds a channel, the doctrine says which criteria may use it
# — but the channel is worthless while the doctrine forbids it.
# ONE MORE THING BEFORE THE FLAG IS FLIPPED. This spec is dispatchable only after
# 134 lands, and 134 edits `factory/verify/models.py`, `factory/verify/factory_yaml.py`,
# `factory/verify/gates.py` and `factory/activities/verify_activities.py` — the two
# files most of this trio's anchors point into. Re-run
# `ergane spec validate specs/144-... --target-repo <this repo> --specs-root specs`
# after 134 has landed and before flipping the flag; the anchors are written in the
# symbol-tier form so that drift is machine-caught at exactly that moment, and
# nothing catches it otherwise.
#
# WHERE THIS CAME FROM. N44 of the `ergane-web` round-3 hand-over, re-verified in the
# 2026-09-03 triage. Twelve stories, four gates, a judge and an independent validation
# all returned green on a visual product with a component clipped off the right edge of
# a 1440px viewport. The gap is NOT that gates cannot render — they can, and the tree
# already knows it: `factory/verify/gate_annotation.py:86` exists because repositories
# declare Playwright, Puppeteer and Cypress gates that drive real browsers. The gap is
# that a render can reach no scorer.
#
# WHAT IT COST, MEASURED. The ledger row
# `verify/nothing-in-the-verification-loop-ever-renders-the-thing-it-is-verifying` is
# `critical`, `open`, two occurrences, first seen 2026-08-29 and last seen 2026-09-03.
# Its second instance is the larger one: a clean install, a clean typecheck, a clean
# build, 497 unit tests and a smoke run that played the game end to end — 200 tiles
# walked, a locked door refused then opened by its key, every weapon fired, a guard
# killed — against a black world in an ordinary browser, 3,604 floor tiles and 720 wall
# faces absent, nothing thrown and no error recorded. Twenty-four stories landed on a
# path nobody ever looked at. The reporter's own method note is the sentence this spec
# is built on: a rendering claim without a picture is not a measurement.
#
# NO `fixes:` KEY IS DECLARED, AND THAT IS A DELIBERATE REFUSAL. The triage entry names
# that critical row under "Findings it would declare". It is not declared here. Read the
# row's notes rather than its name: its mechanism is that the consumer's smoke harness
# drove a headless shell exposing no GPU capability, so a four-line backend selector took
# the other branch on every automated run and the primary rendering path was never once
# executed. The reporter's own fix sentence is about the GATE — "the smoke gate must run
# a browser that reports the capability and assert a non-zero draw count on the SELECTED
# backend". This spec builds no gate and no renderer, by its own charter. Declaring the
# key would let `ergane findings triage --apply` close a critical row on the strength of
# a landed spec that fixed one half, which is the exact shape recorded three times on this
# floor (100, 092, 118) — a critical finding closes, the ledger stops counting recurrences,
# and the promotion path goes quiet on a defect that is still running. Adding the key later
# is one frontmatter line and is legitimate; un-closing a swept row is not. The operator's
# decision, stated as a question: does the platform owning the channel close a row whose
# measured instance was a gate that never rendered? If yes, add the key.
#
# NOT IN SCOPE. This spec does not build a renderer, a browser driver or a screenshot
# verb — a gate is an arbitrary command and repositories already drive real browsers.
# It does not admit an artifact no gate declared. It does not change the diff assembly:
# `factory/workgraph/worktree.py:1496` is untouched, and adding `--binary` there is the
# tempting wrong move (plan.md trap 2). It does not parse or interpret an artifact's
# contents, which stays 134's rule. And it does not delete a single entry from
# `_RUNTIME_MARKERS` — the authoring layer gains a third door, not a smaller list
# (plan.md trap 6).
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail): the judge library entry point was
# wired in (FR-020), the evidence-store codec was wired in (FR-021), the artifacts
# section gained a total bound so a picture can never zero the diff (FR-022), the
# hold's "third input" premise was corrected to the fourth, the D-037 anchor was
# split off D-050's line, FR-007 and FR-013 were reworded, US1's file list was made
# to agree with its tasks, and 34 wrapped symbol anchors were reflowed onto one line.
#
# WHAT CHANGED, AND WHY EACH. An adversarial review refuted this trio on three
# blocking defects, all re-derived from the tree at 602a92c before being repaired.
#
# 1. THE RECORDS HAD NOWHERE TO TRAVEL. plan.md said "Everything FR-013, FR-014 and
# FR-015 ask for happens between" `factory/activities/verify_activities.py:430` and
# `:444`. It does not: that activity calls the library entry point
# `factory/verify/judge.py:752` — `run_judge`, which is the ONLY caller of
# `build_prompt` (`factory/verify/judge.py:798`) and of `parse_verdict`
# (`factory/verify/judge.py:816`) — verified by grep over `factory/`. The trio named
# that function nowhere, so US1 wired nothing through the library and US2's records
# had no parameter to travel on; the cheap wrong move, calling `build_prompt` from
# the activity and bypassing the entry point's retry and malformed-response paths,
# was one line away. FR-020 and US1-S7 now require the parameter, the forward, and
# the flag on BOTH verdict constructions — the parsed one at
# `factory/verify/judge.py:822` and the malformed one at `factory/verify/judge.py:836`,
# which 116 deliberately covers with its own comment.
#
# 2. THE FLAG NEVER REACHED THE ROW. FR-016 requires the flag "false on its recorded
# row" and plan.md's verification steps 3 and 4 both read that row, but the row is
# the evidence store's and its codec is longhand by design: `gates_shown` reaches it
# only because 116 wrote `factory/verify/store.py:1257` and
# `factory/verify/store.py:1281` by hand, and the file's own comment says a field not
# added there gives "a record that round-trips *almost* everything, quietly". No FR,
# task or sizing entry named that file. FR-021 and US1-S8 now do, with the
# absent-reads-false argument copied from the line beside it, and `factory/verify/store.py`
# joins US1's file list. Without this the falsifiable step 4 could not be run at all.
#
# 3. THE ACCOUNTING HAD NO FLOOR. FR-005 copies the gate section's subtraction, but
# that section is safe only because `GATE_OUTPUT_TAIL_LIMIT` is 2 KiB per gate
# (`factory/verify/judge.py:218`). Two 24 KiB pictures encode to ~64 KiB, `prepare_diff`
# is handed a limit of 0, and — read at `factory/verify/judge.py:500` — every section
# is then granted 0 bytes, so the judge is posted a file listing, a truncation notice
# and no diff at all, and scores every scenario anyway. FR-022 bounds the whole
# artifacts section by its own named constant well under `DIFF_INPUT_LIMIT`, records
# past it are withheld with that bound as the reason, and US1-S9 asserts the diff
# section is non-empty when a picture is shown.
#
# MINOR REPAIRS. FR-007 said the prompt must equal "today's in every field" while
# FR-006 adds a field to it; it now says what US1-S2 always said. FR-013's show-limit
# is now stated to sit below 134's own storage bound (134 FR-015), without which its
# over-limit branch is unreachable in production, and the artifact 134 records present
# with no stored location is named as its own withheld case. plan.md § Sizing said
# US1 touches `factory/verify/factory_yaml.py` while T007 said the file needs no edit;
# the contradiction is resolved in favour of a conditional, stated in both places.
# T012 now says the pasted prompt elides the image block's bytes, because pasting an
# assembled prompt verbatim commits the picture base64 into the 64 KiB bound. And 169
# symbol citations were written in the `path.py:NN` — `symbol` form but 34 of them
# wrapped across a source line, where `factory/cli/nouns/spec.py:943`'s per-line
# `finditer` cannot see them — a green validate that proved nothing about those 34
# (the 057 lesson). All 34 are reflowed onto one line.
#
# WHAT WAS NOT CHANGED. No `fixes:` key was added or removed; the refusal above stands
# and the reviewer read the ledger row and agreed with it. The state stays `draft`.
# The hold above keeps its operative decision word for word — the flag may not be
# flipped before the amendment, and no story here edits `.specify/memory/constitution.md`
# — and gains only the correction that the artifact is the fourth input and the
# re-validate step 134's landing makes necessary.
#
# REPAIRED 2026-09-04 (refinement-2026-09-04-tail, second pass): US1 was split at
# 116's own seam because it was oversized against the only precedent that measures
# it; US1-S4's exact-byte accounting claim was restated on the allowance, where it
# is true; US2-S6's control was contradicting the spec's own truth table and is now
# the no-artifact case with the not-present picture folded into US2-S5; US2's
# scenarios now name the library entry point rather than the assembler; FR-013's
# show-limit is strictly below 134's storage bound; specs 133 and 136 are named as
# concurrent drafts on this trio's own files; and the pasted evidence is bounded on
# both halves.
#
# WHY THE SPLIT, MEASURED. Spec 116 built the directly comparable channel in this
# same module and needed three stories: `6f4f0b1` (US1, five scenarios, a 511-line
# test module and 166 lines of `factory/verify/judge.py`) landed at 39,687 diff
# bytes; `f0d2a14` at 44,444; `8f5f633` (US3, the shown flag onto `JudgeVerdict`
# and the store codec, nine files, 883 insertions) at 47,439 — 72% of the 64 KiB
# deterministic refusal at `factory/verify/diffbounds.py:47`. US1 asked one story
# for nine scenarios and strictly more production surface than any of those, which
# the same measured rate puts past the bound: an attempt spent before the judge
# ever runs. The old US1's FR-006, FR-008, FR-020 and FR-021 — the vocabulary, the
# flag, the entry point and the codec — are now US4, dispatched immediately after
# US1 and merging before US2 and US3, which is the cut 116 made and landed green.
# Story numbers are never reused, so the split adds US4 rather than renumbering.
# The scenario ids the entry above names moved with their requirements: the old
# US1-S5, S6, S7 and S8 are now US4-S2, S1, S3 and S4, and the old US1-S9 is
# US1-S5.
#
# WHY THE ACCOUNTING CLAIM MOVED. US1-S4 asked for a diff section "exactly N bytes
# shorter". No correct implementation does that on a natural fixture:
# `factory/verify/judge.py:542` — `_render_section` cuts on whole-line boundaries
# and pays for an elision marker whose width follows the digit count of the number
# it prints (`factory/verify/judge.py:584` — `_marker`), and
# `factory/verify/judge.py:515` — `_allocate` divides in integers. Measured against
# a 13-byte-per-line fixture at a limit of 20,000: N=1 moved the section 0 bytes,
# N=100 moved 91, N=128 moved 130, N=512 moved 507. The allowance handed to
# `prepare_diff` does drop by exactly N, and that is what FR-005 now says. 116 hit
# the same wall and asserted the threshold and the inequality instead
# (`tests/test_116_judge_sees_gates.py:385` and `:406`); US1-S4 now does the same.
#
# WHY US2-S6 COULD NOT BE THE CONTROL IT CLAIMED. Its Given declared an `image` 134
# recorded not present, and its Then asked both for the withheld record FR-004
# assembles as a text line and for a prompt equal to the one assembled with no
# artifact argument. The truth table above separates those two rows on purpose, and
# a prompt carrying that line is not the no-artifact prompt. Written as a control —
# which tasks.md tells the implementer is green from the first commit — it pointed
# at deleting the withheld record from the assembly, which is the honest-degradation
# behaviour this spec exists to add. The not-present picture is now US2-S5's fourth
# record and US2-S6 is the case every repository is actually in.
---

# Feature Specification: the judge can look at what the story built

**Created**: 2026-09-04
**Depends on**: 134-a-gate-declares-the-artifact-it-writes-and-the-platform-carries-it, which puts a gate's declared artifact on `GateResult.artifacts` and stores its bytes. That spec's FR-011 stops one step short on purpose — "the judge's prompt MUST be unchanged by this spec; no collected artifact may reach it" — and this spec is the step it stopped short of. Also an operator amendment to Principle VIII, described in the frontmatter above.

## The gap, stated precisely

A gate can produce a picture. The platform can now carry one. Nothing on the path
from the carrier to the scorer can spell one, so a criterion about what the built
thing looks like is unprovable by construction — and the authoring layer says so
and offers no door that would make it provable.

The chain is five steps, and the fourth is the one the hand-over missed:

1. **Repositories already drive real browsers inside gates, and this tree knows
   it.** `factory/verify/gate_annotation.py:86` is a closed roster of three tools —
   Playwright at `factory/verify/gate_annotation.py:90`, Puppeteer at
   `factory/verify/gate_annotation.py:92`, Cypress at
   `factory/verify/gate_annotation.py:94` — and it exists because those gates
   really run here. A gate that writes a screenshot needs no new mechanism.
2. **134 collects that file and stops.** It puts a `GateArtifact` on
   `GateResult.artifacts` — the tuple lands beside `worktree_writes`
   (`factory/verify/models.py:405` — `GateResult`) — stores the bytes outside the
   worktree and exports a reader. Its FR-011 then forbids exactly one thing: no
   collected artifact may reach the judge's prompt.
3. **The diff cannot carry the file either, and Principle VIII's own escape hatch
   is closed here.** The doctrine says runtime evidence is "committed as an
   artifact the diff contains" (`.specify/memory/constitution.md:72-76`), but the
   judge's input is built by `factory/workgraph/worktree.py:1496` — `diff`, whose
   one patch command is `git diff --cached <base_ref>` at
   `factory/workgraph/worktree.py:1527` — no `--binary`, no `--text`. A committed
   screenshot therefore reaches the judge as the single line
   `Binary files a/shot.png and b/shot.png differ`.
4. **The prompt type forecloses the picture channel.**
   `factory/verify/judge.py:285` — `JudgePrompt` declares
   `messages: list[dict[str, str]]`, and `factory/verify/judge.py:938` — `_complete`
   posts `prompt.messages` verbatim as the body's `messages` to the
   chat-completions path declared at `factory/verify/judge.py:111`. A content
   block — the shape that endpoint takes an image in — cannot be spelled anywhere
   on that path. Nor is there a parameter to carry one: the library entry point
   `factory/verify/judge.py:752` — `run_judge` is the only caller of the assembler
   and of the parser, and it takes gate results and a diff and nothing else.
5. **So the authoring layer refuses the criterion, correctly, and names only two
   remedies.** `factory/cli/nouns/spec.py:1440` is a closed list of fifteen
   phrasings a running system shows and a diff cannot, with `("visually",
   r"visually")` at `factory/cli/nouns/spec.py:1454`;
   `factory/cli/nouns/spec.py:1588` — `_evidence_refusal` offers, at
   `factory/cli/nouns/spec.py:1605` — `_evidence_refusal`, exactly two ways out:
   name a declared gate whose result reaches the judge, or restate the clause as
   something the diff carries. Neither is available to "the header is inside the
   frame", so the honest authoring answer today is *rephrase* — and a criterion
   nobody can write is a criterion nobody scores.

The measured consequence is in the frontmatter: twelve stories, four gates, a
judge and an independent validation all green on a component clipped off a
1440px viewport, and later twenty-four stories landed against a black world.

## The rule this spec is asking for

**A gate's declared picture is admitted to the judge's prompt as a content block,
charged to the same allowance the text sections are and bounded so it can never
spend the whole of it, and only when the judge's persona declares its model can be
shown one — a judge that cannot see records that it did not see, rather than
scoring as though it had.**

The cases are decided by three declarations and nothing else — the artifact's
declared type, the record 134 wrote for it, and the persona registry:

| declared artifact type | what 134's record says | judge persona declares vision | what the prompt carries | `artifacts_shown` |
|---|---|---|---|---|
| `image` | present, with a stored location | yes | the bytes, as one content block, under a named section | **true** |
| `image` | present, with a stored location | **no** | one text line naming gate, path and the persona reason | false |
| `image` | **not present** | yes | one text line naming gate, path and "not written" | false |
| `image` | present, **no stored location** (134 FR-015 declined to store it) | yes | one text line naming gate, path and that the bytes were never stored | false |
| `image` | present, stored, but larger than this spec's per-artifact show-limit | yes | one text line naming gate, path and that limit | false |
| `image` | present, stored, within the show-limit, but the section's total bound is already spent | yes | one text line naming gate, path and that bound | false |
| any other type | — | — | nothing at all | false |
| none declared | — | — | nothing at all; the prompt is byte-identical to today | false |

The last row is the one every existing repository is in, and it is why the
message shape stays a single string until an artifact is actually shown. The two
bounds are separate on purpose: the per-artifact show-limit decides whether one
file's bytes are worth reading at all, and the section bound decides how much of
the judge's whole allowance every picture together may spend, so that the diff
the picture is evidence *about* is still in the prompt beside it.

### What this spec is not

It is not a renderer, a browser driver or a screenshot verb. A gate is an
arbitrary command and the roster at `factory/verify/gate_annotation.py:86` is
proof that repositories already drive browsers with it. Nothing this spec adds
runs a browser.

It is not a change to the diff assembly. `factory/workgraph/worktree.py:1496` — `diff`
keeps its one patch command. Adding `--binary` there would put base64 of
every changed binary inside the allowance the diff is fitted into, and would
silently rewrite every prompt in the corpus.

It is not an implementer's licence to amend Principle VIII. The amendment is an
operator act recorded before dispatch, and no story here edits
`.specify/memory/constitution.md`.

It is not a smaller `_RUNTIME_MARKERS` list. Deleting `("visually", r"visually")`
would admit every unprovable clause in every repository, including the ones this
list was built from. The authoring layer gains a third admission beside
`factory/cli/nouns/spec.py:1513` — `_names_a_declared_gate`, and refuses exactly
as it does today for a repository that declares no picture.

## User Scenarios & Testing

### User Story 1 - The prompt can carry a picture, and the picture is spent from the same allowance the text is (Priority: P1)

As the factory, I can assemble one judge prompt that carries a gate's picture
beside the diff, and the bytes it costs come out of the same allowance the diff
and the gate results are fitted into rather than from nowhere.

**Why this priority**: P1 and everything else reads it. Until `JudgePrompt` can
hold a content block there is nothing for the activity to fill and nothing for a
criterion to name. This story is also where the accounting lives, and accounting
added later is accounting that was wrong in between. It is the pure assembler and
one production file, because that is the size the same work landed at when 116
built it: `6f4f0b1` was five scenarios, a 511-line test module and 166 lines of
`factory/verify/judge.py`, and it measured 39,687 of the 64 KiB a story's diff may
carry (`factory/verify/diffbounds.py:47`). The flag, the entry point and the
stored row are US4, which merges before anything reads them.

**Independent Test**: Assemble a prompt with one artifact record carrying bytes
and one carrying none, and read the assembled messages and the diff section
against the same call made with the artifact argument absent.

**Acceptance Scenarios**:

1. **Given** one artifact record carrying bytes, a declared type of `image`, a
   media type and its producing gate and declared path, **When** the prompt is
   assembled, **Then** the user message's content is a list of typed blocks whose
   image block carries those bytes, the text block immediately before it names
   that gate and that path, and the system prompt states that a shown artifact is
   evidence of the same standing as the gate results — all three asserted by one
   committed test over the assembled object.
2. **Given** no artifact records at all, **When** the prompt is assembled,
   **Then** the user message's content is the single string it is today and the
   assembled object is equal to the one the same criteria, diff and gate results
   produce with the artifact argument absent — one committed test asserting the
   equality, so every prompt the existing corpus compares is unchanged.
3. **Given** one artifact record carrying no bytes and a stated reason, **When**
   the prompt is assembled, **Then** the assembled text carries a line naming that
   gate, that path and that reason, **and** the content carries no image block for
   it — both halves asserted in one committed test, because an assembler that
   simply dropped the record satisfies the second half alone.
4. **Given** a diff that assembles just inside the judge's input limit with no
   artifact record beside it, **When** the same criteria and the same diff are
   assembled again with one artifact record carrying bytes, **Then** the first
   prompt's `truncated_input` is false and the second's is true, **and** the
   second prompt's artifacts section and diff section together are within
   `DIFF_INPUT_LIMIT` — one committed test asserting both halves, modelled on
   `tests/test_116_judge_sees_gates.py:385` — `test_the_gate_section_is_spent_from_the_diffs_own_allowance`
   and its companion at
   `tests/test_116_judge_sees_gates.py:406` — `test_the_gate_section_and_the_diff_together_stay_under_the_input_limit`,
   because an assembler that spent the picture from outside the accounting fits
   the same diff whether or not a picture rides beside it, and one that spent it
   past the limit fails the inequality. The exact-byte claim belongs to the
   allowance and not to the rendered section, which is cut on whole-line
   boundaries (plan.md trap 18).
5. **Given** artifact records whose assembled blocks together measure more than
   the artifacts section's total bound, and a diff long enough to be abridged,
   **When** the prompt is assembled, **Then** the records past that bound carry no
   image block and assemble as text lines naming it, the assembled image blocks
   together are within the bound, and the assembled diff section is not empty —
   one committed test asserting all three, because an assembler with no floor
   hands `factory/verify/judge.py:473` — `prepare_diff` an allowance of zero and
   posts a judge a picture with no code beside it.

### User Story 2 - Only a declared picture reaches the model, only when the judge can be shown one (Priority: P1)

As an operator, the judge sees the file my gate declared as a picture and nothing
else, and if I have routed the judge to a model that cannot be shown one, the row
says so instead of reading like a verdict formed with the picture in hand.

**Why this priority**: P1 and it is the story that makes the channel real. US1's
records can be built by hand; only this story reads what a gate actually declared
and decides what may be shown. It is also the honest-degradation half, which is
the difference between this spec and a silent green.

**Independent Test**: Run the judge activity over gate results carrying one
declared `image` artifact, once with a judge persona declaring vision and once
without, and read the records it hands the library entry point
`factory/verify/judge.py:752` — `run_judge`.

**Acceptance Scenarios**:

1. **Given** a persona registry entry that declares vision beside a persona that
   runs an agent, a second entry that omits the key, and a third that declares it
   on a persona whose agent is the deterministic one, **When** the registry is
   loaded, **Then** the first parses carrying the declaration, the second parses
   carrying its absence, and the third is refused with the field named — one
   committed test over all three, following the refusal `context_window` already
   earns at `factory/config.py:298` — `_build_persona`.
2. **Given** a judge persona resolved from an entry that declares vision, **When**
   the persona is resolved, **Then** the returned `ResolvedPersona` carries the
   declaration, and one decoded from a stored payload written without the field
   carries its absence — one committed test asserting both, and the value reaches
   the judge activity's request rather than stopping at the resolver.
3. **Given** gate results carrying one artifact declared `image` and recorded
   present with a stored location holding known bytes, and a judge persona
   declaring vision, **When** the judge activity assembles its request, **Then**
   the record it hands the library entry point
   `factory/verify/judge.py:752` — `run_judge` carries exactly those bytes and a
   media type derived from the declared path's suffix — asserted by a committed
   test on the bytes themselves and on the argument that entry point was called
   with, so a diff that passed the record through without reading the file fails
   it and so does one that assembles its own prompt instead.
4. **Given** the same gate results and a judge persona that does not declare
   vision, **When** the judge activity assembles its request, **Then** every
   record it hands that entry point carries no bytes and a reason naming the
   persona declaration, **and** the stored file is never opened — proven by a
   committed test whose stored location names a path that does not exist, so an
   implementation that read first and discarded afterwards fails.
5. **Given** four artifacts declared `image` — one recorded present and stored at
   a size larger than the per-artifact show-limit, one recorded present and stored
   a single byte below it, one 134 recorded with its true size and no stored
   location at all, and one 134 recorded as not present — **When** the judge
   activity assembles its request, **Then** the records it hands that entry point
   are, in declaration order, one carrying no bytes and a reason naming that
   limit, one carrying its bytes, one carrying no bytes and a reason naming that
   the bytes were never stored, and one carrying no bytes and the "not written"
   reason, and no stored file is rewritten — one committed test asserting all
   five, so a truncating implementation fails, so does one that treats an unstored
   artifact as absent, and so does one that drops the picture its gate never
   wrote.
6. **Given** gate results carrying declared artifacts of every type other than
   `image` and no artifact of type `image` declared at all, **When** the judge
   activity assembles its request, **Then** it hands the library entry point
   `factory/verify/judge.py:752` — `run_judge` no records at all and the resulting
   prompt is equal to the one the same criteria and diff assemble with the
   artifact argument absent — one committed test asserting both, and it is the
   control: every repository that declares no picture is this case.

### User Story 3 - A criterion about the built artifact is admissible (Priority: P2)

As a spec author, when the target repository declares a picture its gate writes, I
can write the criterion about it and the refinement gate admits it, instead of
telling me to rephrase something that is now provable.

**Why this priority**: P2 because the channel must exist before a criterion may
name it, and it must ship in step: a channel whose criteria are still unwritable
is a channel nobody uses. It touches one module and no production file either
other story touches.

**Independent Test**: Validate one spec twice against two target repositories
differing only in whether their manifest declares an `image` artifact, and read
the exit status, the refusal text and the emitted report.

**Acceptance Scenarios**:

1. **Given** a target repository whose manifest declares an `image` artifact at a
   path, and a spec whose Then-clause carries one of the refused phrasings while
   its scenario names that declared path, **When** the spec is validated, **Then**
   the clause is admitted rather than refused, **and** the same spec against a
   target repository whose manifest declares no `image` artifact is still refused —
   one committed test asserting the pair, because the admitting half alone passes
   on a checker that stopped refusing anything.
2. **Given** a target repository declaring an `image` artifact, and a clause whose
   scenario names neither that artifact nor a declared gate, **When** the spec is
   validated, **Then** it is refused and the refusal names a third remedy — declare
   a picture on a gate and name its path — beside the two it names today, asserted
   by a committed test on the refusal string.
3. **Given** a target repository whose manifest declares no `image` artifact,
   **When** a spec carrying a refused clause is validated, **Then** the refusal
   text is character-for-character the text it is today — the control, asserted by
   a committed test that pins the string, because operators have it in their
   runbooks.
4. **Given** a target repository declaring `image` artifacts, **When** the
   evidence report is emitted, **Then** the emitted document names those declared
   artifacts beside the declared gates it names today, asserted by a committed test
   on the document.

### User Story 4 - `image` is a declarable type, and the row says whether the judge was shown one (Priority: P1)

As an operator reading a verdict back months later, I can tell from the stored row
whether the judge that scored this attempt was shown the picture its gates
declared — and a repository can declare that a gate writes one at all.

**Why this priority**: P1, and it is dispatched second, immediately after US1,
although it is numbered fourth: it was cut out of US1 on sizing grounds and a
story number is never reused. It is everything on the judge's own path that is not
pure assembly — the type vocabulary that makes an `image` declarable, the entry
point the activity's records travel on, and the two longhand codec lines that put
the flag on the stored row. It is one story and not three because a flag defined
in one story and persisted in another is a row that silently reads false in
between; 116 made exactly this cut (`8f5f633`) and landed it green.

**Independent Test**: Load a v2 manifest declaring an `image` artifact; then hand
artifact records to the library entry point over a stubbed transport, read the
flag on both verdicts it can return, and round-trip one verdict through the
evidence store.

**Acceptance Scenarios**:

1. **Given** a v2 manifest declaring an artifact whose type is `image`, **When**
   the manifest is loaded, **Then** the parsed configuration carries that artifact
   with that type, **and** the same manifest with the type spelled `picture` is
   refused with the entry named — one committed test asserting the pair, because
   the accepting half alone passes on a checker that takes any string.
2. **Given** a prompt that assembled at least one image block and a second that
   assembled none, **When** each verdict is parsed, **Then** the first
   `JudgeVerdict` carries the shown flag true and the second carries it false —
   one committed test asserting both, so the row distinguishes a judge shown a
   picture from a judge shown none.
3. **Given** artifact records carrying bytes handed to the library entry point
   `factory/verify/judge.py:752` — `run_judge` over a stubbed transport, **When**
   the call returns a readable response and, in a second call, an unreadable one,
   **Then** both returned verdicts carry the shown flag true — one committed test
   asserting the pair, which fails when the entry point drops the records before
   `factory/verify/judge.py:798` and fails again when the malformed-response
   verdict at `factory/verify/judge.py:836` omits the flag.
4. **Given** a `JudgeVerdict` carrying the shown flag true, **When** it is written
   to the evidence store and read back, **Then** the decoded verdict carries it
   true, **and** a stored document written before this spec — one whose payload
   has no such key — decodes carrying it false: one committed test over
   `factory/verify/store.py:1238` — `_judge_to_dict` and
   `factory/verify/store.py:1261` — `_judge_from_dict`, because a field added to
   the record but not to those two longhand codecs round-trips as false forever
   and nothing else fails.

## Functional Requirements

- **FR-001**: `JudgePrompt.messages` MUST be able to carry a user message whose
  content is a list of typed blocks, in the shape the chat-completions path at
  `factory/verify/judge.py:111` accepts, and `factory/verify/judge.py:918` — `_complete`
  MUST post it unchanged.
- **FR-002**: `factory/verify/judge.py:307` — `build_prompt` MUST take a sequence
  of pure artifact records, each naming its producing gate, the declared
  repo-relative path, the declared type, a media type, and either the artifact's
  bytes or nothing plus a stated reason. It MUST NOT open a path, read the
  filesystem or take a path to read: the bytes arrive as an argument or not at all.
- **FR-003**: A record carrying bytes MUST assemble as one image content block,
  immediately preceded by a text block naming its producing gate and its declared
  path, under a named section heading of its own, modelled on the heading declared
  at `factory/verify/judge.py:197`.
- **FR-004**: A record carrying no bytes MUST assemble as a text line naming its
  gate, its path and the stated reason, and MUST NOT assemble a content block, so
  the judge is told a picture exists and that it was not shown one.
- **FR-005**: The encoded size of every block the artifacts add MUST be subtracted
  from the allowance `factory/verify/judge.py:473` — `prepare_diff` is given, on
  the same measured-not-estimated basis the gate section already uses at
  `factory/verify/judge.py:345` — `build_prompt`, so that allowance is exactly
  that many bytes smaller and no section is spent from outside the accounting. The
  exactness is a claim about the allowance and not about the rendered diff
  section, which `factory/verify/judge.py:542` — `_render_section` cuts on
  whole-line boundaries and charges a variable-width elision marker for (plan.md
  trap 18). FR-022 bounds how much the artifacts may spend.
- **FR-006**: `JudgePrompt` MUST carry whether any image block was assembled, true
  exactly when at least one was, and `factory/verify/judge.py:591` — `parse_verdict`
  MUST carry it onto `JudgeVerdict` as a plain bool written in
  both directions and defaulted, following `gates_shown` at
  `factory/verify/models.py:609` — `JudgeVerdict` and the argument its docstring
  makes at `factory/verify/models.py:594` — `JudgeVerdict`. FR-020 carries it
  through the library entry point and FR-021 onto the stored row.
- **FR-007**: Given no artifact records, the assembled prompt MUST be equal, in
  every field, to the prompt the same criteria, diff and gate results assemble with
  the artifact argument absent — the message shape included, so the user message's
  content is still one string and the existing prompt corpus is unchanged.
- **FR-008**: `image` MUST join the declared artifact-type vocabulary 134 puts on
  the v2 manifest; a manifest declaring an artifact of that type MUST parse and
  carry it, a type outside the widened set MUST still be refused with the entry
  named, and every other declared type MUST parse exactly as it does today.
- **FR-009**: The system prompt MUST state that a shown artifact is evidence of
  the same standing as the gate results and that a scenario naming a declared
  artifact is scored against the artifact shown rather than against a prediction —
  the sentence the prompt already makes about gate results at
  `factory/verify/judge.py:138`.
- **FR-010**: The persona registry MUST accept an optional per-persona declaration
  that the persona's model can be shown an image, absent by default, refused when
  the persona runs no agent — the shape `context_window` has at
  `factory/config.py:170` — `Persona` and `factory/config.py:350` — `_optional_context_window`
  — and a registry declaring it nowhere MUST parse exactly as it does today.
- **FR-011**: `factory/workgraph/models.py:295` — `ResolvedPersona` MUST carry
  that declaration, defaulted so a payload written before this spec still decodes,
  and every site that builds one MUST fill it from the registry entry:
  `factory/activities/agent_activities.py:370` — `resolve_persona`,
  `factory/workgraph/workflow.py:1267` — `_resolve` and
  `factory/workgraph/workflow.py:1285` — `_resolve`.
- **FR-012**: `factory/activities/verify_activities.py:399` — `RunJudgeInput`
  MUST carry whether the judge persona declared it, defaulted absent, and
  `factory/workgraph/workflow.py:2901` — `_score` MUST fill it from the resolved
  judge persona it is already handed.
- **FR-013**: `factory/activities/verify_activities.py:430` — `run_judge` MUST
  build the records it hands the library entry point from the gate results it
  already receives, admitting bytes only for an artifact whose declared type is
  `image`, which 134 recorded present **with a stored location**, whose declared
  path's suffix is inside a named closed set of media types, and whose stored size
  is within a named per-artifact show-limit. That show-limit MUST be this spec's
  own constant and MUST be strictly smaller than the storage bound 134 FR-015
  applies. Strictly, because 134 records an artifact above its bound present with
  no stored location: at equality every artifact that has a stored location is
  already at or below the show-limit, the over-limit branch this requirement
  states is unreachable from any real collector, and it ships green on a synthetic
  fixture. Every other declared artifact of type `image`
  — not present, present but unstored, over the show-limit, or of an unrecognised
  suffix — MUST arrive as a record carrying no bytes and the reason it was not
  shown; an artifact of any other declared type MUST produce no record at all.
- **FR-014**: When the judge persona does not declare vision, every `image`
  artifact MUST arrive as a record carrying no bytes and a reason naming that
  declaration, and no artifact's stored bytes may be read at all.
- **FR-015**: The bytes MUST be read inside the activity, from the stored location
  the artifact record names, and never in workflow code, which may read neither
  filesystem nor environment; a stored location that cannot be read MUST produce a
  record carrying no bytes and a reason naming the read failure rather than
  raising, so an unreadable file costs a note in the prompt and not the attempt.
- **FR-016**: An attempt whose gates declared no `image` artifact MUST reach the
  judge exactly as it does today, with the shown flag false on the row FR-021
  writes.
- **FR-017**: `factory/cli/nouns/spec.py:1781` — `_check_evidence` MUST admit a
  Then-clause carrying a refused phrasing when its scenario names, by declared
  path, an artifact the target repository's manifest declares with type `image` —
  a third admission beside `factory/cli/nouns/spec.py:1513` — `_names_a_declared_gate`
  — because that artifact now reaches the judge with the
  diff. No entry may be removed from the list at
  `factory/cli/nouns/spec.py:1440`.
- **FR-018**: The refusal built at `factory/cli/nouns/spec.py:1588` — `_evidence_refusal`
  MUST name a third remedy — declaring a picture on a gate and
  naming its path — beside the two it names today, when and only when the target
  repository's manifest declares at least one `image` artifact; for a manifest
  that declares none, the refusal text MUST be character-for-character what it is
  today.
- **FR-019**: The emitted evidence report MUST state the declared `image`
  artifacts beside the declared gates it already states at
  `factory/cli/nouns/spec.py:1685` — `as_dict`, and a clause admitted by an
  artifact MUST be counted as provable rather than reported as borderline.
- **FR-020**: `factory/verify/judge.py:752` — `run_judge`, the only caller of the
  assembler and of the parser, MUST take the artifact records as an argument
  defaulted to none, forward them to `build_prompt` at
  `factory/verify/judge.py:798`, and carry the assembled prompt's shown flag onto
  **both** verdicts it can return — the parsed one, beside `gates_shown` at
  `factory/verify/judge.py:822`, and the malformed-response one, beside
  `gates_shown` at `factory/verify/judge.py:836` — because what the judge was shown
  is a fact about the ask and an ask that produced garbage was still made with, or
  without, the picture in it. A caller that passes no records MUST get today's
  prompt and today's verdict.
- **FR-021**: The evidence store's verdict codec MUST write the shown flag beside
  `gates_shown` at `factory/verify/store.py:1257` and read it back with an absent
  key defaulting to false at `factory/verify/store.py:1281`, so a row written
  before this spec decodes as a judge that was shown nothing and the flag FR-016
  and the operator's verification both read is actually on the row. The codec is
  longhand by design and derives nothing.
- **FR-022**: The artifacts section's total encoded size MUST be bounded by one
  named constant well below `DIFF_INPUT_LIMIT` (`factory/verify/diffbounds.py:47`),
  on the per-gate model `factory/verify/judge.py:218` already uses for gate output;
  a record whose block would carry the running total past that bound MUST assemble
  as a text line naming the bound and carry no image block, in declaration order,
  so the diff section is never reduced to nothing by the pictures that are evidence
  about it.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-007, FR-009, FR-022]
US4:
  depends_on: []
  depends_on_merged: [US1]
  implements: [FR-006, FR-008, FR-020, FR-021]
US2:
  depends_on: []
  depends_on_merged: [US4]
  implements: [FR-010, FR-011, FR-012, FR-013, FR-014, FR-015, FR-016]
US3:
  depends_on: []
  depends_on_merged: [US4]
  implements: [FR-017, FR-018, FR-019]
```

Three `depends_on_merged` edges, all declared rather than left inferred (069-US2
FR-007), and no `depends_on` edge at all: nothing here needs another story's
worktree, only its landed code. US4 merges after US1 because it reads what US1
assembles — the shown flag is true exactly when US1's assembler emitted an image
block, and the records US4 forwards travel on the parameter US1 puts on
`factory/verify/judge.py:307` — `build_prompt`. It is also the only pair in this
graph that shares a production file, and the edge is what makes that safe. US2
constructs the artifact records US1 defines, hands them to the entry-point
parameter US4 adds and reads the `image` type US4 adds to the manifest
vocabulary, so it merges after US4 — and behind US4, after US1 — or it has
nothing to construct and nowhere to hand it. US3 reads that same `image` type off
a target repository's parsed manifest, so it merges after US4 for that reason and
for no other; it never touches the assembler, the entry point or the store.

US2 and US3 declare no edge between them because they share no production file
and no requirement: US2 lives in `factory/config.py`,
`factory/workgraph/models.py`, `factory/activities/agent_activities.py`,
`factory/workgraph/workflow.py` and `factory/activities/verify_activities.py`,
and US3 lives in `factory/cli/nouns/spec.py` alone. Neither names US1's file
(`factory/verify/judge.py`) or US4's (`factory/verify/judge.py`,
`factory/verify/models.py`, `factory/verify/store.py` and, only if 134's landed
reader spells its type set a second time, `factory/verify/factory_yaml.py`) other
than to call into them. The one shared file in the graph is
`factory/verify/judge.py`, held by US1 and US4, which the merge edge orders.
