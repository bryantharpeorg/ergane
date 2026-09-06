---
state: draft
fixes:
  - verify/judge-passes-a-story-that-states-its-own-requirement-unmet
# DRAFTED 2026-09-04 by the refinement workflow (refinement-2026-09-04) from
# docs/triage-2026-09-03-ergane-web-round3.md § "a-story-can-land-with-a-requirement-open-and-say-so"
# (lines 184-200), against ergane-buildout at 602a92c. Every `file:line` in
# spec.md and plan.md was read from that commit and verified to resolve to the
# symbol named, not recalled.
# REPAIRED 2026-09-04 (refinement-2026-09-04), against ergane-buildout at
# 602a92c, after an adversarial review: the readiness refusal moved off
# `_attested_resolver` onto `compute_readiness`'s dependency loop, because the
# observed resolver the roadmap workflow and `ergane status` inject is consulted
# first and would have made the whole of FR-011 inert — US3-S7 is the new
# observed-landed leg that proves it; the triage refusal moved off
# `_declared_index` onto the declared-class branch, because dropping a spec from
# that index routes its row to the prose-candidate class with a reason that is
# false about it and names no requirement; US2 now waits on US3 merged, because
# the paste-ready line US2 prints is a key the grammar refuses until US3 lands
# and one unknown key refuses the whole corpus read; FR-010 reworded to one
# *extraction* point rather than one reader, FR-012 to name the readiness field
# `rendered_state` actually reads, FR-014 to forbid the candidate class;
# `VerificationResult` carries 23 fields, not 24. No key removed, no key added,
# no story renumbered, no hold lifted. State stays draft.
# REPAIRED 2026-09-04 (refinement-2026-09-04, second pass), against
# ergane-buildout at 602a92c, after a second adversarial review found tasks.md
# an hour older than the repaired spec.md and plan.md and still ordering, in the
# imperative, both of the builds the first repair had forbidden. tasks.md is
# re-cut whole against the fourteen-trap plan: the readiness refusal now goes
# into `compute_readiness`'s dependency loop above both resolvers and the triage
# refusal into `_class_declared` with the spec kept in the declared index; the
# two scenarios the gate reported with no task (US2-S7, US3-S7) each gained one,
# and US3-S7 is the leg that catches the inert build; the `SpecReadiness` field
# `rendered_state` cannot be written without is split into its own task; the
# trap citations on the two triage tasks moved from 10 to 13; and the DDL is
# anchored at its `CREATE TABLE` rather than at `_migrate`. `factory/worker.py`
# is now named as US2's sixth production file in both file lists, and plan.md's
# Sizing no longer understates US3's pasted evidence. One reported defect was
# declined with evidence: the thirteen `SYMBOL` (`path:NN`) citations name
# module-level constants, and the validator's `_symbol_spans` maps only
# `FunctionDef`, `AsyncFunctionDef` and `ClassDef`, so rewriting them in the
# dash form would refuse the gate — proven by running the validator's own two
# functions over all six. No key removed, no key added, no story renumbered, no
# hold lifted. State stays draft.
# REPAIRED 2026-09-04 (refinement-2026-09-04, third pass), against
# ergane-buildout at 602a92c, after a third adversarial review found one blocking
# contradiction and six cheaper faults. FR-015's "report byte-identically" and
# US3-S5's true-flag control could not both hold, because the `--json` document
# is exactly {default_branch, facts, unlanded} today
# (`factory/workgraph/cli.py:205-222`): FR-015 now declares that one additive
# field as its single, named exception, so an implementer no longer has to choose
# which MUST to break. The flag is renamed `no_open_requirements` and forbidden
# from reading as a landing claim, because `complete` on the surface whose job is
# landings would be this spec's own defect pointed the other way. FR-010 no
# longer obliges FR-011 and FR-012 to consult a frontmatter reader neither ever
# holds. FR-012 is scoped to a spec whose declared state is `landed`, matching
# the `amended` guard at `factory/roadmap/models.py:546`. FR-014 now discounts
# only the incomplete declarer, so a second, complete spec still proves its own
# finding and triage does not regress for specs that declare nothing. FR-009
# prints ONE aggregated paste-ready entry for the epic rather than one per
# attempt, because `factory/roadmap/models.py:260` — `_parse_frontmatter` resolves
# a key written twice last-wins in silence, which would lose an honestly declared
# requirement — the invisibility this spec exists to end. plan.md gains trap 15
# for that, and its Sizing and operator sequence now name the two critical open
# interpreter findings US1 and US2 land on top of. No key removed, no key added,
# no story renumbered, no scenario renumbered, no hold lifted. State stays draft.
# REPAIRED 2026-09-04 (refinement-2026-09-04, fourth pass), against ergane-buildout
# at 602a92c, after a fourth adversarial review found one blocking defect: US2
# ordered a NEW per-attempt activity into the epic workflow with no version guard,
# while `tests/test_interpreter.py:2953` --
# `test_replay_032_fixtures_replay_green` replays ten committed histories whose
# recorded attempt path is exactly run_agent_attempt,
# detect_operator_question_activity, run_gates -- so all ten would have gone red at
# gate time, and the repair an implementer reaches for first (re-recording the
# fixtures) is forbidden by that test's own docstring. The spec now decides the
# mechanism rather than leaving it to the implementer's debugger: the scan is
# folded into the existing `detect_operator_question_activity`, which already reads
# that transcript at that point, so the recorded command sequence never moves and
# no `workflow.patched` marker is spent. FR-006 and FR-008 say so, US2-S8 is the
# new leg that proves it, and plan.md trap 16 names the rejected alternative
# (118-US3's patch marker at `factory/workgraph/workflow.py:1826`), the forbidden
# repair, and the two wrong moves inside the chosen one. Three cheaper faults went
# with it: `factory/worker.py` leaves US2's file list because no activity is
# registered; FR-013 and FR-015 now emit both `--json` keys unconditionally, so a
# spec that declares nothing has one document shape rather than two; and the
# operator sequence no longer calls the boolean a completeness flag. No key
# removed, no key added, no story renumbered, no scenario renumbered, no hold
# lifted. State stays draft.
#
# WHERE THIS CAME FROM. The P1 entry of the `ergane-web` round-3 triage. A node
# blocked by a binding rule shipped an honest fallback whose own source file says
# it does not do what its MUST requires; the judge passed it twice; every
# downstream reader calls the spec landed. The ledger row
# (`verify/judge-passes-a-story-that-states-its-own-requirement-unmet`, warning,
# open, one occurrence, first seen 2026-09-03) carries the triage's own
# correction to the report: the tree is *worse* than the report says, because the
# landed reader filters to `RequirementKind.STORY` and an unmet FR is outside its
# domain entirely rather than merely indistinguishable.
#
# WHAT IT COST, MEASURED. One story landed on the branch whose own text says a
# requirement is unmet, passed by the judge twice — and the operator's answer to
# the node's question arrived six minutes after the story had already landed, so
# it was spent. The ledger grades the row `warning` at one occurrence. The
# uncounted cost is the ledger's: `findings triage --apply` closes a finding on
# the strength of a landed spec's `fixes:` declaration, and three dated instances
# on this floor (100, 092, 118) are already half-fixes that closed whole. A spec
# that lands with a requirement open is that failure with the evidence sitting in
# its own frontmatter, unread.
#
# NOT IN SCOPE, AND THE FIRST IS A REFUSAL. There is NO third `OverallVerdict`:
# `factory/verify/models.py:16-19` declares its absence as an invariant and edge
# unlocking reads only that value, so the fact is carried beside the verdict and
# never inside it. The judge is not made to score FR-### requirements. The node's
# stop-and-ask behaviour, which was correct, is untouched. The six-minute-late
# operator answer is noted in plan.md's trap 6 and deliberately not scoped: a
# question whose answer arrives after the attempt closes is a different defect.
# Nothing here writes the frontmatter automatically — the record and the report
# hand the operator the exact line, and the operator writes it; an automatic
# writer would be a fourth author of a spec's frontmatter and is left out on
# purpose. And one residual is left open on purpose, so whoever reads the closed
# ledger row can see it: this spec gives an honest deferral a channel and teaches
# it in the prompt (FR-005), but the recorded occurrence used no channel at all —
# it named its deviation in source comments — and nothing here detects a
# deviation stated only in a comment. A node that stays silent is still
# indistinguishable after this spec ships.
#
# ONE KEY, FIFTEEN FRs, AND THE HALF-FIX CHECK RUN FORWARDS. The single declared
# key names both halves of its own summary — "indistinguishable from a met one"
# (US1 and US2 make it distinguishable on the record and on the attempt report)
# and the triage's harder half, "no downstream surface can see it" (US3 makes
# three surfaces see it). No key was removed and none was added: the ledger holds
# exactly one row for this defect.
---

# Feature Specification: a story can land with a requirement open and say so

**Created**: 2026-09-04
**Depends on**: nothing.

## The gap, stated precisely

An honestly deferred requirement and a met one are the same object at every
surface the factory has. The chain is six steps, and the first is not a defect.

1. The verdict vocabulary is binary **on purpose**. `factory/verify/models.py:16-19`
   states the absence of a third `OverallVerdict` as an invariant: a judge that
   was unreachable is a PASS carrying `judge_unavailable`, "not a separate
   'unknown' that downstream code could accidentally treat as passing". Edge
   unlocking reads that value and nothing else. This is right, and it is why the
   fact has to be carried somewhere else.
2. Nowhere else on the row can hold it. `factory/verify/models.py:860` —
   `VerificationResult` carries 23 fields, and every one of them is a qualifier on
   *how* the verdict was reached — `judge_unavailable`, `criteria_drift`,
   `gate_contradictions`, `provenance`, `base_ref`, `dispatch`, `persona`,
   `model_alias`, `route`. None names a requirement the attempt left open, and
   `grep -rniE "outstanding|deferred|waived|unmet|unsatisfied" factory/verify/`
   returns nothing relevant.
3. An FR-only node has no scorer at all. `factory/verify/models.py:967` —
   `has_scenarios` reports False for a node owing only `FR-###` bullets, and
   `factory/verify/judge.py:333-341` raises rather than dispatching an empty
   scenario list, because "an empty dispatched list would parse back as 'every
   scenario passed'". Such a node is gates-plus-output-check by design. In the
   reported case the FUNCTIONAL MUST therefore had no scorer anywhere unless some
   story's acceptance scenario happened to restate it.
4. The landed report cannot see it either — and this is the half the source
   report missed. `factory/workgraph/cli.py:168` — `landed_command` builds its
   declared list at `factory/workgraph/cli.py:199-203` by filtering to
   `RequirementKind.STORY`, and `factory/workgraph/landed.py:395` —
   `_story_keys` filters the same way for the facts side. An unmet FR is outside
   the report's domain, not merely indistinguishable within it.
5. The frontmatter cannot say it. `_KNOWN_KEYS` (`factory/roadmap/models.py:117`)
   is closed at `("state", "depends_on_landed", "fixes")` and refuses anything
   else at `factory/roadmap/models.py:308-316`, inside
   `factory/roadmap/models.py:296` — `_shape_entry`;
   `factory/roadmap/models.py:66` — `SpecState` is draft/ready/deferred/landed and
   admits no fifth value. There is no key and no value for this today.
6. And the attestation is what closes findings. `factory/doctor/triage.py:583` —
   `_declared_index` counts a `fixes:` declaration only from a spec whose
   frontmatter attests `landed` (`factory/doctor/triage.py:161` — `landed`), and
   `factory/doctor/triage.py:496-503` offers that declared class before every
   other class, so a spec that landed with a requirement still open closes, by
   declaration, the very finding it declared. That is the half-fix this floor has
   already paid for three times, with the evidence sitting unread in the spec's
   own frontmatter.

**Two near misses exist and neither reaches this.** `factory/cli/nouns/spec.py:1781`
— `_check_evidence` refuses a Then-clause naming a runtime outcome no declared
gate measures, and `continue`s past every requirement that is not
`RequirementKind.STORY`. `factory/verify/remediation.py:191` — `screen_feedback`
preserves an unsatisfiability report for the operator, but
`factory/verify/remediation.py:186` — `reports_unsatisfiable` only feeds the path
where the judge FAILS. And `factory/verify/question.py:85` —
`detect_operator_question` parks an attempt; it does not annotate a landing.

## The rule this spec is asking for

**A story may land with a named requirement recorded as open — the attempt record
carries which one, the attempt report hands the operator the line to write it
down, and no spec-level reader calls the spec complete while one is open — and
the verdict vocabulary stays exactly two values.**

The four cases, complete:

| node declares a requirement open | frontmatter declares one | verdict and landing | spec reads complete |
|---|---|---|---|
| no | no | today's, byte-identical | yes — today, unchanged |
| yes | no | unchanged; the row names the requirement | yes, and the attempt report prints the line to paste |
| yes | yes | unchanged; the row names the requirement | **no** — three readers refuse |
| no | yes | unchanged | **no** — the operator's word stands on its own |

### What this spec is not

It is not a third verdict. `OverallVerdict` keeps exactly two members, the
composed verdict is unchanged by the new field, and edge unlocking reads what it
read before.

It is not an exemption for the node. The gates, the output check and the judge run
exactly as they do today on an attempt that declares an open requirement; the
declaration buys the node nothing and costs its spec something. It is a
confession, not a waiver.

It is not per-requirement scoring. Nothing here measures whether an FR was met,
and `ergane spec landed` still reports landings for stories only — what changes is
that a requirement *declared* open becomes visible there. Making the judge score
FR-### bullets is a different spec and is ruled out here.

It is not an automatic frontmatter writer. The record and the attempt report name
the requirement and print the exact line; a human puts it in the spec.

It is not a detector of silence. The marker is the node's own act. An attempt that
leaves a requirement open and says nothing — which is what the recorded occurrence
did, naming its deviation in source comments — is untouched by everything here.

## User Scenarios & Testing

### User Story 1 - The attempt record can name a requirement the story left open (Priority: P1)

As the operator reading an epic's evidence, an attempt that left a named
requirement open says so on its own row, without the verdict changing meaning.

**Why this priority**: P1 and it depends on nothing. It is the carrier every other
story writes into or reads from, and it is the story where the invariant is at
risk: the obvious wrong build is a third verdict.

**Independent Test**: Compose a result with and without a named open requirement,
write both to a store file, read them back, and compare the rows field by field.

**Acceptance Scenarios**:

1. **Given** an attempt that recorded no open requirement, **When** its result is
   composed, **Then** the new field is empty and every other field, `verdict`
   included, is what today's composition produces for the same inputs — the
   control that every attempt already in the store is.
2. **Given** the same gate results, output check and judge verdict composed twice,
   once naming an open requirement and once not, **When** both are composed,
   **Then** the two results differ in that one field alone and their `verdict`
   values are equal, proven by a committed test that compares the two objects
   field by field.
3. **Given** a result carrying two named open requirements, **When** it is written
   to a store file and read back, **Then** the round trip returns the same two
   names in the same order.
4. **Given** a store file created before this column existed, **When** it is
   opened, **Then** the column is added after `route`, the recorded schema version
   is the new one, and a row written before the column reads back as empty; a
   committed test asserts the migrated store's column list equals a freshly
   created store's, column for column and in the same order.
5. **Given** the verdict vocabulary, **When** the members of `OverallVerdict` are
   enumerated, **Then** a committed test asserts there are exactly two and names
   them, so this spec's carrier cannot become a third verdict by later drift.

### User Story 2 - A node can say which requirement it left open, and the record receives it (Priority: P2)

As an implementer blocked by a binding rule, I can name the requirement I left
open in my final message, and it reaches the record instead of only my source
comments.

**Why this priority**: P2, and it is the only story that waits on others — US1's
field is where it writes, and US3's grammar is what makes the line it prints
paste-able. It is also the story that decides whether the mechanism is real: a
detector nothing teaches is dead code, and a marker that short-circuits grading is
a free pass.

**Independent Test**: Scan a transcript carrying the marker and one carrying a
quoted mention of it; verify one attempt with the marker and one without over
identical gate results and compare the composed verdicts.

**Acceptance Scenarios**:

1. **Given** an archived final message carrying `## OPEN REQUIREMENT` as a
   line-anchored level-2 heading with a body naming `FR-007`, **When** the
   transcript is scanned, **Then** the detector returns `FR-007` and nothing else.
2. **Given** the same heading quoted inside prose, inside a fenced block, or at a
   different heading level, **When** the transcript is scanned, **Then** no
   requirement is returned, because a mention of the marker is not a marker — the
   grammar `detect_operator_question` already draws, reused rather than reinvented.
3. **Given** a marker whose body names nothing matching the requirement-key
   grammar, **When** the transcript is scanned, **Then** no requirement is
   returned and the attempt is graded exactly as an attempt carrying no marker.
4. **Given** two attempts with identical gate results, output check and judge
   verdict, one whose transcript carries the marker and one whose does not,
   **When** each is verified, **Then** both compose the same `verdict`, their nodes
   reach the same termination, and only the recorded open-requirement field
   differs — asserted by a committed test in the scripted-world harness whose
   detection fake is `tests/test_interpreter.py:1689` —
   `detect_operator_question_activity`, because `VerificationResult` carries no
   termination (`factory/verify/models.py:925-947`): the termination is decided in
   the workflow's node loop, so half of this scenario is observable only there.
5. **Given** the assembled implementer prompt, **When** it is built, **Then** it
   contains the heading the detector matches, asserted by a committed test that
   reads the detector's own constant rather than a second copy of the string, so
   the two sides of the contract cannot drift apart.
6. **Given** one epic with two recorded attempts declaring different open
   requirements and a third declaring none, **When** the attempt report text is
   produced, **Then** each declaring attempt's requirement is named under its own
   line, the attempt declaring none gains no line, and the report carries exactly
   one paste-ready `open_requirements:` frontmatter entry naming both
   requirements — asserted by a committed test, because two entries pasted into
   one block are one YAML key written twice and the last one wins in silence;
   and an epic whose attempts declare none produces neither the lines nor the
   entry.
7. **Given** the paste-ready line the report prints, **When** a committed test
   feeds that exact line into the corpus reader as a landed spec's frontmatter,
   **Then** the corpus parses and the entry carries the requirement — the line the
   operator is told to paste is a line the grammar accepts, asserted rather than
   assumed.
8. **Given** one attempt whose transcript carries the marker and one whose does
   not, **When** each is run in the scripted-world harness, **Then** the two
   recorded activity sequences are equal and neither names an activity type that
   did not exist before this story, asserted by a committed test; and the ten
   committed histories under `tests/fixtures/replay-032/` still replay under the
   changed workflow, proven by the unchanged standing guard
   `tests/test_interpreter.py:2953` — `test_replay_032_fixtures_replay_green`,
   with its output pasted as committed evidence and those ten fixture files absent
   from the story's diff.

### User Story 3 - A spec with an open requirement is not complete (Priority: P1)

As the operator, a spec that landed with a requirement open does not satisfy a
dependant, does not read as landed, and does not close a finding by declaration.

**Why this priority**: P1 despite being third, and it depends on nothing — it can
land before either of the others and be used the day it does, by writing the key
by hand. It is also the half that stops the ledger crediting a half-fix, which is
the uncounted cost in this spec's provenance, and it is the grammar US2's printed
line needs to exist.

**Independent Test**: Parse a corpus in which one landed spec declares an open
requirement, compute readiness for a spec that depends on it under both resolvers,
run the landed report over it, and triage a finding it declares.

**Acceptance Scenarios**:

1. **Given** a spec whose frontmatter declares `open_requirements: [FR-007]`
   beside `state: landed`, **When** the corpus is parsed, **Then** it parses and
   the entry carries that list.
2. **Given** a spec declaring `open_requirements: FR-007` as a scalar rather than
   a list, **When** the corpus is parsed, **Then** it is refused with a message
   naming the key and the required shape, on the same path `fixes:` is refused —
   a scalar read as a list is a list of characters, which is a defect this
   repository has already paid for.
3. **Given** a corpus in which no spec declares the key, **When** it is parsed and
   its readiness computed, **Then** both are identical to today's, because every
   spec now in the corpus is that spec. A committed test asserts the equality.
4. **Given** spec A attested `landed` with one open requirement and spec B whose
   `depends_on_landed` names A, **When** readiness is computed with no injected
   resolver, **Then** B names A among its blockers and A's rendered state is not
   `landed`; and a committed test asserts that the same corpus with A's key
   removed makes B dispatchable, so only the declaration moved the answer.
5. **Given** spec A, **When** `ergane spec landed` reports on it, **Then** the
   report names FR-007 as open, the `--json` document carries it under
   `open_requirements`, and the document's `no_open_requirements` field is false —
   with the same spec minus the key producing an empty `open_requirements`, that
   field true, and `default_branch`, `facts` and `unlanded` exactly as today's
   document has them; the same committed test asserts the document's whole key set
   in both states, so a key emitted only sometimes fails it.
6. **Given** a finding whose only declaring spec is A and whose `last_seen`
   predates A's landing commit, **When** triage classifies it, **Then** it is not
   classified fixed, it is not classified as a prose candidate, and its reason
   names A and A's open requirement — because an attestation from a spec that says
   it is not finished is not a proof, and a row a human must read must say why;
   and, in the same committed test, that same finding declared *also* by a second
   landed spec carrying no open requirement still classifies fixed on that second
   spec's proof, so discounting A costs no other spec its own.
7. **Given** the same corpus and a `landed_for` resolver that reports A
   observed-landed — the resolver shape `factory/roadmap/workflow.py:1331` —
   `_observed_resolver` and `factory/cli/status.py:441` —
   `_observed_landed_resolver` inject on the two live paths — **When** readiness is
   computed, **Then** B still names A among its blockers, proven by a committed
   test that injects that resolver, so the refusal cannot be bypassed by the
   resolver the roadmap actually dispatches on.

## Functional Requirements

- **FR-001**: `VerificationResult` MUST carry an additive field naming the
  requirements the attempt recorded as open, defaulting to empty, and
  `compose_result` MUST carry it onto the row without consulting it when deriving
  `verdict`.
- **FR-002**: `OverallVerdict` MUST keep exactly two members. The open-requirement
  fact MUST NOT become a third verdict, a third termination, or a second gate, and
  a committed test MUST assert the membership.
- **FR-003**: The evidence store MUST persist the field additively: one new column
  placed last in the DDL after `route`, the schema version bumped, the migration
  appended after the columns 117-US2 added, and NULL read back as empty rather
  than backfilled.
- **FR-004**: A non-empty value MUST round-trip through the store unchanged, and a
  store created before the column MUST migrate in place to the same column order
  as a freshly created store.
- **FR-005**: The implementer prompt MUST teach the marker, and the heading it
  teaches MUST be the same constant the detector matches — one value read from one
  place, never two copies of a string.
- **FR-006**: The detector MUST read requirement keys from the last line-anchored
  `## OPEN REQUIREMENT` heading in the agent's final message, reusing the
  fence-masking and heading grammar `factory/verify/question.py:85` —
  `detect_operator_question` already uses; a mention inside prose or inside a
  fenced block MUST NOT be a marker. The scan MUST be carried by the activity that
  already reads that transcript at that point in the attempt —
  `factory/activities/verify_activities.py:371` —
  `detect_operator_question_activity` — which MUST return the keys as a new field
  on its result type, `factory/verify/question.py:71` — `QuestionMarker`, with an
  empty default. No new activity type is added, and no second activity call is
  scheduled on the attempt path.
- **FR-007**: A marker whose body yields no key matching the requirement-key
  grammar MUST record nothing, and the attempt MUST be graded as one carrying no
  marker at all.
- **FR-008**: The marker MUST NOT change the verdict, the termination, the gate or
  judge path, or the retry ladder. It is recorded in addition to grading, never
  instead of it. The epic workflow's recorded command sequence MUST NOT move
  either: no activity call is added to the attempt path, so the ten committed
  histories under `tests/fixtures/replay-032/` replay unchanged and no
  `workflow.patched` marker is spent on this story. The new field on the
  activity's result MUST carry an empty default, because every history recorded
  before it has no such key in its recorded payload. The ten fixture files MUST
  NOT be re-recorded and MUST NOT appear in the story's diff.
- **FR-009**: The attempt report MUST name each recorded open requirement under
  its attempt's line, and MUST print exactly one paste-ready `open_requirements:`
  frontmatter entry per epic, naming every requirement recorded across that
  epic's attempts, deduplicated and in a deterministic order. It MUST NOT print
  one entry per attempt: two entries pasted into one frontmatter block are one
  YAML key written twice, and `factory/roadmap/models.py:260` —
  `_parse_frontmatter` takes the last of them with no error, so one honestly
  declared requirement would vanish. An epic that recorded none MUST print
  neither the per-attempt lines nor the entry. The printed entry MUST be one the
  corpus grammar accepts, asserted by a committed test that parses it.
- **FR-010**: The spec frontmatter grammar MUST accept `open_requirements`, a list
  of requirement keys, validated exactly as `fixes:` is and refusing a scalar. One
  function MUST be the only place the key is *extracted from a frontmatter block*,
  and FR-013 and FR-014 — the two readers that hold a block — MUST consult that
  function rather than parsing it again. FR-011 and FR-012 read no block at all
  and are not bound by that sentence: they consume the value off
  `factory/roadmap/models.py:126` — `SpecEntry`, as
  `factory/roadmap/models.py:296` — `_shape_entry` populated it. The roadmap's own
  shape check stays the one place the shape is refused.
- **FR-011**: A spec declaring one or more open requirements MUST NOT satisfy
  another spec's `depends_on_landed` edge, whether that spec is attested landed or
  observed landed; the dependant names it among its blockers. The refusal MUST be
  decided above both resolvers, so that an injected `landed_for` reporting the
  dependency landed cannot bypass it.
- **FR-012**: Readiness MUST carry the declaration onto its computed per-spec
  record, beside `drifted`, and MUST render such a spec in a state distinct from
  `landed`, following the `amended` precedent at `factory/roadmap/models.py:544` —
  `rendered_state`. The new rendering *replaces* `landed` and MUST apply only when
  the declared state is `landed`, guarded exactly as `amended` is at
  `factory/roadmap/models.py:546`: a draft or ready spec that declares an open
  requirement renders today's value unchanged. Where both apply, the declared
  requirement MUST take precedence over `amended`.
- **FR-013**: `ergane spec landed` MUST name every declared open requirement in
  both its human output and its `--json` document. The document MUST carry exactly
  two additive keys, both emitted for every spec so the document keeps one shape:
  `open_requirements`, the list of requirements the spec declares open, empty when
  it declares none; and one boolean named for what it actually measures —
  `no_open_requirements`, true when the spec declares none and false while any
  declared requirement is open. It MUST NOT be named or documented as a completeness or landing claim: it
  says nothing about whether the spec's stories landed, which the document's
  `unlanded` list (`factory/workgraph/cli.py:205-222`) already answers, and a
  boolean called complete on the surface whose whole job is reporting landings
  would be a new false claim of exactly the kind this spec exists to stop.
- **FR-014**: `ergane findings triage` MUST NOT treat a spec's `fixes:`
  declaration as proof of a fix while that spec declares an open requirement. That
  spec's declaration MUST be discounted and the finding classified from the
  declaring specs that remain, exactly as today — the rule
  `factory/doctor/triage.py:613` — `_class_declared` already states, that a
  finding several specs declare is fixed when any of them proves it, MUST survive
  intact, so a second, complete declarer still closes it. Only when every
  declaring spec declares an open requirement MUST the finding be classified into
  the class a human reads, with a reason naming the declaring spec and its open
  requirement. It MUST NOT reach the prose candidate class, whose reason would say
  no spec declares it.
- **FR-015**: A spec that does not declare `open_requirements` MUST parse, compute
  readiness, report and triage byte-identically to today, with exactly one
  exception, declared here so no implementer has to choose between two MUSTs: the
  `ergane spec landed --json` document gains the two additive keys FR-013 names —
  `open_requirements`, reading as an empty list, and `no_open_requirements`,
  reading true. Both are emitted for every spec, declaring or not, so a spec that
  declares nothing yields the same key set as one that declares something rather
  than a second shape of the document. Nothing else about that document moves — `default_branch`, `facts` and `unlanded`
  (`factory/workgraph/cli.py:205-222`) keep their shapes and their contents — and
  the human output, the parse, the readiness and the triage of such a spec do not
  move at all.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004]
US2:
  depends_on: []
  depends_on_merged: [US1, US3]
  implements: [FR-005, FR-006, FR-007, FR-008, FR-009]
US3:
  depends_on: []
  implements: [FR-010, FR-011, FR-012, FR-013, FR-014, FR-015]
```

Two edges, both declared rather than left to inference (069-US2 FR-007), and both
on US2. US2 writes into the field US1 adds to `VerificationResult` and reads it
back in the attempt report, so it needs US1 merged. US2 also *prints* an
`open_requirements:` line and tells the operator to paste it, and until US3 widens
`_KNOWN_KEYS` that line is an unknown key: `factory/roadmap/models.py:416-419`
says `read_roadmap` "raises `RoadmapError` naming every fault, and yields no
partial roadmap", so one pasted line would refuse the whole corpus read — the
roadmap's dispatch, `ergane status`, `ergane roadmap render` and every
`ergane spec validate` in the tree — until US3 landed. US2 therefore waits for US3
merged too. Both are `depends_on_merged` rather than `depends_on` because the
three share no production file and the edges buy sequencing alone — US1 is
`factory/verify/models.py` and `factory/verify/store.py`, US2 is
`factory/workgraph/prompt.py`, `factory/verify/question.py`,
`factory/activities/verify_activities.py` (the existing detection activity,
widened rather than joined by a second one — trap 16),
`factory/workgraph/workflow.py` and
`factory/cli/nouns/build.py`, US3 is `factory/roadmap/models.py`,
`factory/workgraph/cli.py` and `factory/doctor/triage.py`.

US3 declares no edge at all, and that is deliberate rather than an oversight: it
opens no file either other story opens and it reads nothing US1 or US2 writes. It
is the operator-facing half and is usable on its own the day it lands, with the
key written by hand. US1 and US3 may run in either order or at once; US2 is last.
