# Implementation Plan: a story can land with a requirement open and say so

Every `file:line` below was read from `ergane-buildout` at `602a92c` on
2026-09-04 and verified to resolve to the symbol named. Do not trust an anchor
that has moved; re-read before editing.

## What already exists, and where

**The invariant this spec must not break is written down as prose in the module
that holds the type.** `factory/verify/models.py:16-19`:

```
- There is no third overall verdict. `OverallVerdict` has exactly PASS and FAIL
  because those are the only two values edge unlocking can read (FR-005) — a
  judge that was unreachable is a PASS carrying `judge_unavailable`, not a
  separate "unknown" that downstream code could accidentally treat as passing.
```

Read it before writing a line of US1. Every fact this spec adds is carried
*beside* the verdict.

**The row to widen, and the shape every previous widening took.**
`factory/verify/models.py:860` — `VerificationResult` is a frozen dataclass of 23
fields (`factory/verify/models.py:925-947`), whose last six are the four most
recent additions — `base_ref` (118-US2), `gate_contradictions` (116-US3),
`dispatch` (117-US1) and the routing trio (117-US2) — each with a default:

```python
    base_ref: str = UNKNOWN_BASE_REF
    gate_contradictions: tuple[GateContradiction, ...] = ()
    dispatch: str = UNKNOWN_DISPATCH
    persona: str = UNKNOWN_BUILDER
    model_alias: str = UNKNOWN_BUILDER
    route: str = UNKNOWN_BUILDER
```

`gate_contradictions` is the nearest precedent in kind as well as in shape: a
tuple, defaulting empty, whose empty value means "the check ran and found
nothing" rather than "not checked". Copy it. `factory/verify/models.py:998` —
`compose_result` is where it is threaded, and its docstring already argues three
times over why a fact about an attempt is *passed in* rather than re-derived
there; the new field is the fourth instance of the same argument.

**The store's ladder, and the one ordering rule that matters.**
`SCHEMA_VERSION` (`factory/verify/store.py:175`) is 13, with one comment
paragraph per version above it — write the fourteenth in the same voice.
`factory/verify/store.py:556` — `_migrate` applies them; the result-column block
ends with the three columns 117-US2 added, and the comment above it states the
rule in the tree's own words at `factory/verify/store.py:641`:

```python
    if result_columns and "persona" not in result_columns:
        # 117-US2, and the order is the whole trick (plan trap 2). These run
        # *after* the rebuild above, never before: `ALTER TABLE ADD COLUMN`
        # appends, the rebuild puts `dispatch` last, and a store that gained
        # these three first would come out of the rebuild with `dispatch` behind
        # them while a fresh store has it in front. `_RESULT_COLUMNS` is read
        # positionally, so a divergent order does not raise — it hands every
        # field of every row to the wrong attribute.
```

The loop that applies them is `factory/verify/store.py:650`. `_RESULT_COLUMNS`
(`factory/verify/store.py:711`) is the positional list, written and read through
`factory/verify/store.py:850` — `upsert_result` and
`factory/verify/store.py:1031` — `_result_from_row`.

**The DDL itself is a contract file inside another spec's directory.**
`specs/002-verification-gating/contracts/verification-store.sql:65-67` holds
`persona`, `model_alias` and `route` immediately before the `UNIQUE` clause.
Editing it is legitimate and has precedent: 126-US3 (`94c8cd8`) and 117-US1/US2
(`27dd5ca`, `1cae431`) each did. Edit the `.sql` contract and nothing else in
that directory — never that spec's `spec.md`, `plan.md` or `tasks.md`.

**The marker machinery to extend is one small module with a stated contract.**
`factory/verify/question.py:85` — `detect_operator_question` returns
`factory/verify/question.py:71` — `QuestionMarker`, matching the constant
`QUESTION_HEADING` (`factory/verify/question.py:51`). It reads the archive
through `factory/verify/question.py:119` — `_read_stdout` and finds the heading
with `factory/verify/question.py:152` — `_last_marker`, which reuses the criteria
parser's `HEADER_RE`, `mask_fences` and `section_end` so that "what is a heading
and what is quoted text about one" is decided one way across the factory. The new
detector belongs in this module, beside that one, reusing both helpers. A second
module with its own transcript reader would be a second answer to a question this
one already answers.

**The other half of that contract is the prompt.** `_OPERATOR_QUESTION`
(`factory/workgraph/prompt.py:258`) is the section that teaches the heading, and
the sentence that names it is `factory/workgraph/prompt.py:280`. It is assembled
unconditionally at `factory/workgraph/prompt.py:571-572`, beside `_GATE_BOUNDARY`
and behind no input. The new section goes in the same list, the same way. Note
that `factory/workgraph/prompt.py:280` writes the heading as a literal, not as a
format of the constant: US2-S5 asks for the stricter thing, so the new section is
where the constant is formatted in, not a second copy of a habit.

**Where the marker is detected in the epic, and where the result is composed.**
`factory/workgraph/workflow.py:1940-1946` is the question detection call, run
before gates and judge precisely so a question never influences the verdict path.
The composition is far away, in `factory/workgraph/workflow.py:2559` — `_verify`,
whose two keyword-only parameters `provenance` and `routing`
(`factory/workgraph/workflow.py:2568-2570`) are the precedent for the new one:
both are facts about the attempt handed in by the caller. Not every value at the
compose site is: `base_ref` comes off `prepared.base_ref`, and
`dispatch=workflow.info().run_id` is read *inside* `_verify` — do not copy that
one, because an open requirement is a fact only the caller's detector knows.
`_verify` has three call sites — `factory/workgraph/workflow.py:2076`,
`factory/workgraph/workflow.py:2871` and `factory/workgraph/workflow.py:4005` —
so a new keyword-only parameter with an empty default leaves the other two
byte-identical. The `compose_result` call is at
`factory/workgraph/workflow.py:2653`.

**The attempt report, and the precedent for an extra indented line.**
`factory/cli/nouns/build.py:1352` — `render_attempts` prints one line per attempt
and appends `factory/cli/nouns/build.py:1398` — `_contradiction_lines` under it.
Read that function's docstring before writing FR-009: it states why extra lines
rather than another token, and why silence on the ordinary attempt is the
record's own answer. `factory/cli/nouns/build.py:1284` — `attempts_command` is
the caller. The "print the exact line to paste" half has its own precedent in
`factory/workgraph/cli.py:168` — `landed_command`, which prints the exact PR title
and trailer a rescue must carry.

**The frontmatter grammar, and how the last key was added to it.** `_KNOWN_KEYS`
(`factory/roadmap/models.py:117`) carries its own reasoning:

```python
#: `fixes` is 073-US1's one addition, and the closure is why it is one name and
#: not a metadata block: widening the grammar is a visible act, and the refusal
#: below quotes this tuple back at an author who typed anything else.
_KNOWN_KEYS = ("state", "depends_on_landed", "fixes")
```

`factory/roadmap/models.py:296` — `_shape_entry` refuses unknown keys at
`factory/roadmap/models.py:308-316` and then type-checks `depends_on_landed` and
`fixes` one after the other; the `fixes` block is the exact template for the new
one, comment included. The entry it builds is `factory/roadmap/models.py:126` —
`SpecEntry`.

**And that refusal is corpus-wide, which is why US2 waits for US3.**
`factory/roadmap/models.py:411` — `read_roadmap` says so in its own docstring at
`factory/roadmap/models.py:416-419`: "A malformed corpus — one where any spec's
frontmatter fails the grammar — still raises `RoadmapError` naming every fault,
and yields no partial roadmap". One spec carrying an unknown key takes down the
roadmap read for every spec, and `factory/cli/nouns/spec.py:999` —
`_check_frontmatter` calls `read_roadmap` too, so `ergane spec validate` on any
spec in the tree reports it as well.

**The three readers, and the one parse they already share.**
`factory/roadmap/models.py:240` — `_split_frontmatter` is imported across module
boundaries today: `factory/doctor/triage.py:80` reads
`from factory.roadmap.models import SPEC_NAME, _split_frontmatter`, and
`factory/doctor/triage.py:281` — `_declaration` pulls `state` and `fixes` out of
one block for `factory/doctor/triage.py:233` — `read_spec_records`, which builds
`factory/doctor/triage.py:140` — `SpecRecord` and its
`factory/doctor/triage.py:161` — `landed` property.

**Where triage decides, and the order it decides in.**
`factory/doctor/triage.py:470` — `classify` offers the declared classes first, at
`factory/doctor/triage.py:496-503`:

```python
    declared = _declared_index(records)
    remaining: list[Finding] = []
    for finding in pool:
        specs = declared.get(finding.key)
        if specs:
            triaged.append(_class_declared(finding, specs, landing_date_for))
        else:
            remaining.append(finding)
```

`factory/doctor/triage.py:583` — `_declared_index` is the index (its docstring
already says FR-005 "rests on the attestation as much as on the declaration") and
`factory/doctor/triage.py:613` — `_class_declared` is the branch that splits one
declared finding into fixed / seen-after-fix / undated and writes the reason
string. That is where a fourth outcome belongs. The classes it can reach are
`factory/doctor/triage.py:115` — `TriageClass`; `NEEDS_HUMAN` is annotated and
never closed (`factory/doctor/triage.py:772`), which is the behaviour FR-014
wants.

**Readiness, and why the refusal cannot live in one resolver.**
`factory/roadmap/models.py:504` — `_attested_resolver` answers "does this spec's
own frontmatter say landed", and `factory/roadmap/models.py:570` —
`compute_readiness` consults it **second**:

```python
        for dependency in entry.depends_on_landed:
            status = observed(dependency)
            if status is None or not status.landed:
                status = attested(dependency)
            if status is not None and status.landed:
                satisfied_as[dependency] = status.kind
            else:
                blockers.append(dependency)
```

(`factory/roadmap/models.py:598-605`.) `observed` is the injected `landed_for`
(`factory/roadmap/models.py:591`), and both live callers inject one:
`factory/roadmap/workflow.py:689` and `factory/roadmap/workflow.py:853` pass
`landed_for=self._observed_resolver()` (`factory/roadmap/workflow.py:1331`),
which answers from the specs the running roadmap has watched a child land for;
`factory/cli/status.py:292` passes the git-derived
`factory/cli/status.py:441` — `_observed_landed_resolver`. So a refusal written
inside `_attested_resolver` is skipped for exactly the specs the roadmap just
landed. The declaration has to be read in the loop above, before either resolver
is asked. `factory/roadmap/models.py:544` — `rendered_state` is the read-only
override that prints `RENDERED_AMENDED` (`factory/roadmap/models.py:91`) in place
of `landed`; it reads `self.drifted` and `self.state` off
`factory/roadmap/models.py:516` — `SpecReadiness`, so FR-012 needs a field there
too, populated at the construction in `factory/roadmap/models.py:609-618`.

**The landed report's story filter, which is step 4 of the gap.**
`factory/workgraph/cli.py:199-203` is:

```python
    declared = [
        (requirement.key, requirement.title)
        for requirement in requirements
        if requirement.kind is RequirementKind.STORY
    ]
```

and `factory/workgraph/landed.py:395` — `_story_keys` filters the same way for the
facts side. Neither is wrong; both are why an FR is invisible here.

**And the exact document FR-013 adds a field to.** `factory/workgraph/cli.py:205-222`
builds it, and it is three keys and no more:

```python
    if getattr(args, "as_json", False):
        document: dict[str, Any] = {"default_branch": default_branch, "facts": {}}
        for story_key, fact in sorted(facts.items()):
            document["facts"][story_key] = asdict(fact)
        document["unlanded"] = [
```

Count them before writing FR-013: `default_branch`, `facts`, `unlanded`. FR-015
says a spec declaring nothing is byte-identical to today *apart from* the one
additive `no_open_requirements` field, and that exception is written into FR-015
on purpose — the two MUSTs were in direct contradiction until it was, and an
implementer who resolved it either way failed the other. Add one key, leave the
other three alone, and emit it unconditionally: a field that appears only
sometimes is a second shape of the same document.

## Traps

**Trap 1 — The gap is wider than the report, and the over-correction is worse
than the gap.** FR-013. `factory/workgraph/cli.py:199-203` and
`factory/workgraph/landed.py:395` — `_story_keys` filter the declared list to
`RequirementKind.STORY`, so an unmet FR is outside the landed report's domain
entirely. The tempting fix is to drop the filter and enumerate every FR beside the
stories. Do not: nothing in the factory measures whether an FR was met, so every
enumerated FR would print as "no landing yet" forever, complete with a rescue PR
title for a requirement that is not a node. Report the requirements the frontmatter
*declares* open, and leave the story filter exactly as it is. The same care governs
the field's *name*: FR-013 calls it `no_open_requirements`, not `complete`, because
this document's whole subject is landings and a boolean called complete would read
true for a spec with zero landed stories that happens to declare no requirement.
That is a new false claim on an operator surface — this spec's own defect class,
pointed the other way — and naming the field for what it measures is the whole
defence.

**Trap 2 — An FR-only node has no scorer, and this spec does not give it one.**
`factory/verify/models.py:967` — `has_scenarios` returns False for a node owing
only `FR-###` bullets, and `factory/verify/judge.py:333-341` raises rather than
dispatching an empty scenario list. In the reported case the FUNCTIONAL MUST
therefore had no scorer anywhere. An implementer who reads that as the root cause
will be tempted to make the judge score FR bullets. That is ruled out in spec.md
and it is not what the finding asks for: the ask is that the *absence* be
recorded, not that it be graded.

**Trap 3 — The frontmatter is a closed grammar, and `state:` is not where this
goes.** FR-010. `_KNOWN_KEYS` (`factory/roadmap/models.py:117`) is three names and
`factory/roadmap/models.py:296` — `_shape_entry` quotes the tuple back at an
author who typed anything else. The cheap-looking alternative is a fifth
`SpecState` value — but `factory/roadmap/models.py:66` — `SpecState` is what the
roadmap dispatches on, `building` is deliberately absent from it because "only the
system may say building", and a fifth value would make every `state ==` comparison
in the corpus a place that has to be re-read. Widen the key set by one name,
type-check it exactly as `fixes` is type-checked immediately below, and say in the
commit that widening the grammar is a visible act.

**Trap 4 — The carrier must be new; there is nothing to reuse.** FR-001.
`factory/verify/models.py:860` — `VerificationResult` has 23 fields and every one
is a qualifier on how the verdict was reached. `provenance` is who completed the
work; `criteria_drift` is that the spec moved under the node; `judge_unavailable`
is that the judge could not be reached. Overloading any of them puts two facts in
one slot, which is the defect
`interpreter/the-ref-clearing-report-overwrites-the-terminal-reason-that-explains-why-a-node-died`
records against 126-US2 from exactly this shape of shortcut. Add a field.

**Trap 5 — Two near misses exist, and neither is this.** `factory/cli/nouns/spec.py:1781`
— `_check_evidence` is 102's evidence layer: it refuses Then-clauses naming a
runtime outcome no declared gate measures, and `continue`s past every requirement
that is not `RequirementKind.STORY`, so it never sees an FR.
`factory/verify/remediation.py:191` — `screen_feedback` preserves an
unsatisfiability report through `factory/verify/remediation.py:186` —
`reports_unsatisfiable`, but only on the path where the judge FAILS; a passing
attempt's report goes nowhere. And `factory/verify/question.py:85` —
`detect_operator_question` parks an attempt rather than annotating a landing. An
implementer who wires this spec into any of the three will produce something that
works in one of the four cases in spec.md's table.

**Trap 6 — Note the six-minute answer; do not scope it in.** In the reported case
the operator's answer arrived six minutes *after* the story had landed, so it was
spent. That is a real defect about the lifetime of a parked question and it has
nothing to do with the carrier, the grammar or the three readers. If you find
yourself editing `factory/verify/question.py`'s parking path or the question
child-workflow, you have left this spec.

**Trap 7 — Column order is the whole trick, and getting it wrong does not raise.**
FR-003, FR-004. `_RESULT_COLUMNS` (`factory/verify/store.py:711`) is read
positionally by `factory/verify/store.py:1031` — `_result_from_row`, and
`factory/verify/store.py:641` says what a divergent order costs: "it hands every
field of every row to the wrong attribute". The new column goes **last** in the
DDL — after `route` at
`specs/002-verification-gating/contracts/verification-store.sql:65-67` and before
the `UNIQUE` clause — and its `ALTER TABLE` runs **after** the persona loop at
`factory/verify/store.py:650` inside `factory/verify/store.py:556` — `_migrate`.
An implementer who adds it alphabetically, or who puts the ALTER beside
`gate_contradictions` where the block reads more naturally, ships a store that
passes every fresh-database test and mangles every migrated one. US1-S4 is the
scenario that catches it, and it must compare column *order*, not membership.

**Trap 8 — A marker nothing teaches is dead code that passes every test.** FR-005.
`QUESTION_HEADING` (`factory/verify/question.py:51`) is matched by the detector and
taught by `_OPERATOR_QUESTION` (`factory/workgraph/prompt.py:258`), whose sentence
is at `factory/workgraph/prompt.py:280`, assembled at
`factory/workgraph/prompt.py:571-572`. A US2 that adds a detector, an activity and
a store write but no prompt section is green everywhere and no agent ever writes
the marker: the whole story lands as a mechanism that cannot fire. Add the section
to the same unconditional list, and let the new section format the detector's
constant rather than repeating the string — `factory/workgraph/prompt.py:280`
writes its own heading as a literal, so this is the one place not to copy the
neighbour. US2-S5 asserts exactly that, and the reason is that two copies of a
heading is a contract with two definitions.

**Trap 9 — Do not copy the question path's control flow.** FR-008.
`factory/workgraph/workflow.py:1940-1946` detects the question marker *before*
gates and judge, and on a hit it sets `Termination.QUESTION`, salvages and parks —
by design, because a question attempt has nothing to grade. Copying that structure
is the most likely wrong build in this whole spec: it would turn a confession into
a free pass, letting a node skip the judge by naming a requirement. This marker
changes no branch. Detect it, carry the keys to `factory/workgraph/workflow.py:2559`
— `_verify` as a keyword-only argument with an empty default beside `provenance`
and `routing`, and pass them through `compose_result` at
`factory/workgraph/workflow.py:2653`. US2-S4 is the test that both attempts
compose the same verdict and the same termination; write it first.

**Trap 10 — The refusal must sit above both resolvers, or it is inert exactly
where the roadmap dispatches.** FR-011, FR-012. The obvious site is
`factory/roadmap/models.py:504` — `_attested_resolver`, four lines that answer
"does this spec attest landed". It is the wrong site.
`factory/roadmap/models.py:598-605` asks the *observed* resolver first and only
falls through to the attested one when it returns `None` or not-landed, and both
live callers inject an observed resolver — `factory/roadmap/workflow.py:689` and
`factory/roadmap/workflow.py:853` inject
`factory/roadmap/workflow.py:1331` — `_observed_resolver`, which reports landed for
every spec the running roadmap has watched a child complete, and
`factory/cli/status.py:292` injects
`factory/cli/status.py:441` — `_observed_landed_resolver`. A spec that just landed
with a requirement open is precisely the spec the observed resolver answers for,
so an attested-only refusal is skipped in the dispatch loop and skipped on the
status board, while a unit test that injects no resolver passes green. Put the
check in `factory/roadmap/models.py:570` — `compute_readiness`'s dependency loop,
before `observed` is called: a dependency whose entry declares an open requirement
is a blocker whatever either resolver would have said. US3-S7 is the leg that
proves it, and it must inject a resolver reporting the dependency landed.

**Trap 11 — Three readers, one parse.** FR-010. `factory/doctor/triage.py:80`
already imports `_split_frontmatter` from `factory.roadmap.models`, so the shared
*extraction* belongs in `factory/roadmap/models.py` and the other two import it.
That is one function for "what does this block declare open", not one function for
everything: the two existing parses deliberately disagree in strictness —
`factory/doctor/triage.py:281` — `_declaration` reads leniently so a sweep over
sixty-nine specs is not stopped by one typo, while
`factory/roadmap/models.py:296` — `_shape_entry` refuses — and that split stays.
The roadmap keeps being the one place the *shape* is refused; the shared function
is the one place the *value* is read. A third parse written inside
`factory/workgraph/cli.py:168` — `landed_command` would make "is this spec
complete" a question with three answers, one of them silently lenient. Note which
FRs that binds: FR-013 and FR-014 hold a frontmatter block and must import the
function. FR-011 and FR-012 never see one — `factory/roadmap/models.py:570` —
`compute_readiness` has no file access at all and `factory/roadmap/models.py:544` —
`rendered_state` reads two fields off a dataclass — so they consume the value off
`factory/roadmap/models.py:126` — `SpecEntry` as `factory/roadmap/models.py:296` —
`_shape_entry` populated it. An implementer who reads "one function, four readers"
as an instruction to give `compute_readiness` a parser has misread it.

**Trap 12 — `rendered_state` needs a precedence rule, and the spec picked one.**
FR-012. `factory/roadmap/models.py:544` — `rendered_state` currently returns
`RENDERED_AMENDED` (`factory/roadmap/models.py:91`) when a `landed` spec has
drifted. It reads two fields off `factory/roadmap/models.py:516` —
`SpecReadiness`, and the open-requirement fact is on `SpecEntry`, not there: the
branch cannot be written until a field is added beside `drifted` and populated in
the construction at `factory/roadmap/models.py:609-618`. A spec can be both
drifted and incomplete, and an implementer who adds a second branch without
deciding which wins will pick one by accident of line order. The declared
requirement wins: drift is an observation that the text moved, incompleteness is
the author's own statement about the work. Assert the precedence in a test rather
than leaving it to the reader of the `if` chain. And copy the *guard* as well as
the shape: `factory/roadmap/models.py:546` is `if self.drifted and self.state is
SpecState.LANDED`, so `amended` can only ever replace `landed`. The new branch is
the same — it replaces `landed` and nothing else. Written ungated it would change
the rendered state of every *draft* or *ready* spec that declares the key, on the
status board, for a spec that never claimed to be finished; T028 exercises only
the landed case, so nothing in the suite would catch it.

**Trap 13 — Dropping the spec from the declared index is not the refusal; it is a
lie about the spec.** FR-014. The one-line-looking fix is to make
`factory/doctor/triage.py:583` — `_declared_index` skip a spec that declares an
open requirement. Follow that through `factory/doctor/triage.py:470` — `classify`:
the row falls past the declared classes, past fragmentation, and into the prose
scan at `factory/doctor/triage.py:528-546`, which classifies it `CANDIDATE` with
the reason "named in the prose of landed spec X, but no 'fixes:' declares it —
prose is not a declaration". Every clause of that sentence is false about a spec
whose `fixes:` does declare it, it names no open requirement, and `CANDIDATE` is
one of the classes `--apply` may never touch, so the operator gets a wrong reason
instead of a right one. `factory/doctor/triage.py:307` — `_prose` states the
invariant being broken in its own docstring at
`factory/doctor/triage.py:317-323`: "Including the block cannot leak a declaration
into the candidate class, because the declared classes are offered first".
`_declared_index` returns `dict[str, list[str]]` and cannot carry a reason anyway.
Keep the spec in the index and branch inside
`factory/doctor/triage.py:613` — `_class_declared`, which is already the function
that decides which class a declared finding lands in and writes the sentence the
operator reads. It will need the open requirements alongside the spec dirs — carry
them on `factory/doctor/triage.py:140` — `SpecRecord` and hand them in, the way
`landing_date_for` is handed in. Inside that function, discount the incomplete
declarer rather than the finding: its docstring states the rule the branch must
keep — "A finding several specs declare is fixed when *any* of them proves it" —
so drop the incomplete spec from the list the branch reasons over and let the
remaining declarers classify it exactly as today. Only when that list empties does
the row go to `NEEDS_HUMAN`. A branch written as "any declarer is incomplete
therefore the finding needs a human" regresses triage for a *complete* spec that
declares nothing wrong, which FR-015 forbids, and nothing in the reported
occurrence asked for it.

**Trap 14 — The grammar must exist before the line that tells an operator to type
it.** FR-009, FR-010. US2 prints a paste-ready `open_requirements:` entry; until
US3 lands, that key is unknown to `factory/roadmap/models.py:296` —
`_shape_entry`, and `factory/roadmap/models.py:416-419` says one bad entry makes
`read_roadmap` "raise `RoadmapError` naming every fault, and yield no partial
roadmap". An operator who follows the printed instruction in that window loses the
roadmap's dispatch, `ergane status`, `ergane roadmap render` and every
`ergane spec validate` in the tree at once, for the whole corpus, until US3 lands
or the line is deleted. The Work Graph therefore has US2 waiting on US3 merged as
well as US1; do not remove that edge because the two stories share no file, and do
not print the entry from a story that landed before the grammar. US2-S7 asserts
the printed line is one the corpus reader accepts.

**Trap 15 — Two attempts, two printed entries, one requirement lost in silence.**
FR-009. `factory/cli/nouns/build.py:1352` — `render_attempts` is handed every
result for the epic and prints one line per attempt, so the obvious build prints
the paste-ready `open_requirements:` entry the same way: once under each declaring
attempt. Follow that to the operator's hands. Two attempts declaring different
requirements print two entries; an operator doing what the report tells him copies
both into one frontmatter block; `factory/roadmap/models.py:260` —
`_parse_frontmatter` calls `yaml.safe_load` at `factory/roadmap/models.py:271`,
which resolves a key written twice last-wins with no error, no warning and no
finding. One honestly declared requirement then disappears — which is the exact
invisibility this spec exists to end, reintroduced by its own remedy. Print the
per-attempt naming lines per attempt and the paste-ready entry **once per epic**,
aggregating every requirement recorded across its attempts, deduplicated and
deterministically ordered. US2-S6 is the scenario that catches it and its Given
carries two declaring attempts on purpose.

## Sizing

US1 touches `factory/verify/models.py`, `factory/verify/store.py` and
`specs/002-verification-gating/contracts/verification-store.sql` — one field, one
column, one migration branch, one schema-version paragraph — plus tests in the
store's and the models' existing test modules.

US2 touches six production files, not five: `factory/workgraph/prompt.py` (one
section constant and one line in the assembly list), `factory/verify/question.py`
(one detector beside the existing one, reusing its reader and its heading
finder), `factory/activities/verify_activities.py` (one activity modelled on
`factory/activities/verify_activities.py:371` — `detect_operator_question_activity`),
`factory/worker.py` (one line registering that activity at
`factory/worker.py:142`, beside the existing one — an activity nothing registers
is not callable, so this file is production, not paperwork),
`factory/workgraph/workflow.py` (the detection call, one keyword-only parameter on
`_verify`, one argument at the compose site) and `factory/cli/nouns/build.py` (one
line-builder beside `_contradiction_lines`). Its only reach outside those files is
a test: US2-S7 parses the line it prints through the corpus reader, which is why
US2 waits on US3 merged rather than merely on US1.

Two of US2's edits are small in diff and large in blast radius, and both are named
open critical findings rather than speculation. The new activity adds a name to
`factory/activities/verify_activities.py`, which the workflow imports at
`factory/workgraph/workflow.py:187` inside the passthrough block opened at
`factory/workgraph/workflow.py:119` — the shape
`interpreter/a-landed-activity-type-blocks-every-new-epic-until-the-worker-restarts`
records twice, most recently against 118-US2 whose whole purpose was adding
`base_ref` to the verification record; US1 widens
`factory/verify/models.py`, imported the same way at
`factory/workgraph/workflow.py:231`, so it is in the same class the moment it adds
a name the workflow imports. And the detection call at
`factory/workgraph/workflow.py:1940-1946` adds a command to the epic workflow's
recorded sequence, which is
`interpreter/a-landed-change-to-the-landing-path-makes-every-in-flight-epic-unreplayable`
— two epics lost at once on 2026-08-20 when the adopting restart replayed against
a sequence that no longer matched. Neither is fixable in this spec; both are the
operator's, and step 2 below says what to do about them.

US3 touches `factory/roadmap/models.py` (the key in `_KNOWN_KEYS`, the type-check
in `_shape_entry`, the field on `SpecEntry`, the shared extraction function, the
dependency-loop check and a field on `SpecReadiness` populated in
`compute_readiness`, and the branch in `rendered_state`),
`factory/workgraph/cli.py` (the report and the JSON document) and
`factory/doctor/triage.py` (`SpecRecord`, its one-parse declaration reader, and
the fourth outcome in `_class_declared`).

US1 and US3 name no production file in common; US2 names none in common with
either — `factory/worker.py` included, which neither of the other two opens. The
two edges are US1 → US2 and US3 → US2, and both are merge edges rather than
contention edges.

All three are well inside the 64 KiB deterministic diff bound (D-050). The
largest production diff is US2's, roughly 200 lines across six files, and its
pasted evidence is one attempt-report excerpt. US3's production diff is smaller —
roughly 150 to 250 lines across three modules — but its evidence is the heaviest
in the spec: three surfaces in two states each, six short documents, because
steps 4 to 6 below are the falsifying pair and a single surface would not falsify
anything. If that paste crowds the bound, split it into the declared-state half
and the deleted-state half and say which pair falsifies; do not drop a surface.

## Verification the operator will run, independent of the gate

Per constitution VIII and D-037 the judge sees the diff and the criteria only, so
runtime evidence is committed as pasted output. Beyond that:

1. Open a store written before this spec (`ergane build attempts <epic>` against an
   existing epic is enough to force the migration), then dump
   `PRAGMA table_info(verification_results)` for that store and for a freshly
   created one, and diff the two column lists. They must be identical in order,
   not merely in membership. This is trap 7 run forwards.
2. With the floor empty — no epic in flight — restart the worker before
   dispatching anything, and only then dispatch one story whose agent writes
   `## OPEN REQUIREMENT` naming one of its own FRs. Both halves matter and both
   are open critical findings, not caution. US2 adds a name to a module the
   workflow imports passthrough, so a worker still running the old code fails
   every *new* epic at import —
   `interpreter/a-landed-activity-type-blocks-every-new-epic-until-the-worker-restarts`,
   two occurrences. US2 also adds a command to the epic workflow's recorded
   sequence, so the restart that adopts it makes every *in-flight* epic
   unreplayable —
   `interpreter/a-landed-change-to-the-landing-path-makes-every-in-flight-epic-unreplayable`,
   which cost two epics at once. Restarting on an empty floor is the one order
   that satisfies both. Then confirm the story still lands: same verdict, same
   termination, a merged PR. The declaration must cost the node nothing.
3. Run `ergane build attempts <epic>` for that epic and confirm the attempt's line
   carries the requirement and the paste-ready frontmatter entry beneath it.
4. Paste that entry into a scratch spec whose `state:` is `landed`, then run
   `ergane roadmap render`, `ergane spec landed <spec-dir>` and
   `ergane findings triage` over a corpus containing it and a second spec that
   depends on it. The dependant must park naming it, the landed report must name
   the open requirement with a false completeness flag, and a finding the spec
   declares must classify to the human class with a reason naming the spec and the
   requirement — not to `candidate` (trap 13).
5. Repeat step 4's readiness half with `ergane status`, whose resolver derives
   landings from git rather than from the attestation (`factory/cli/status.py:441`
   — `_observed_landed_resolver`). The dependant must park there too; if it does
   not, the refusal went into `_attested_resolver` and trap 10 caught nobody.
6. Delete the line and re-run all four. Every one must return to today's answer.

Steps 4 to 6 together are the falsifiable test of the whole spec: they are the
three surfaces that called a half-finished spec complete, run forwards on both
readiness paths and then back.
