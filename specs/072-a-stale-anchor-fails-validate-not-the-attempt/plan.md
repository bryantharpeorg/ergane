# Implementation Plan: a stale anchor fails validate, not the attempt

**Spec**: `specs/072-a-stale-anchor-fails-validate-not-the-attempt/spec.md`

## Read this first: this plan's own anchors rotted, and validate passed it clean

Every line below was re-read and verified against `3a93604` on **2026-09-01**. The
previous revision was verified against `357d227` on 2026-08-20 and, twelve days
later, three of its six citations were wrong:

| cited as | actually at | drift |
| --- | --- | --- |
| factory/cli/nouns/spec.py:230-390 — `_validate_command` | `483-728` | −253 |
| factory/cli/nouns/spec.py:223-227 — `_ValidateFinding.__init__` | `477-480` | −254 |
| factory/cli/nouns/spec.py:480-517 — `_check_scenario_coverage` | `923-960` | −443 |

The three `factory/verify/criteria.py` citations did **not** move and were exact.
So the rule is re-verify, not assume-rotten — but the number worth carrying is
this one: **`:480` still resolves to a real, non-blank line.** It is
`self.severity = severity`, four lines inside `_ValidateFinding`. An implementer
sent to "spec.py:480-517 — `_check_scenario_coverage`, copy its shape" opens a
class body that plausibly belongs to the same subject, and nothing announces the
error.

That is the whole spec in one artifact, and it carries a design consequence:
**US1 alone would not have caught any of the three.** All three files exist, all
three lines are inside the file, none is blank. Only US2's symbol check sees
them. US1 is the cheap tier; US2 is the tier that pays.

## What already exists, and where

**The validate command you are extending** — `factory/cli/nouns/spec.py`, 1409
lines:

- `factory/cli/nouns/spec.py:483-728` — `_validate_command`. It has grown from
  six layers to **nine** since this spec was drafted. Read all of it before
  adding the tenth; two of the nine did not exist in August.
- `factory/cli/nouns/spec.py:476-480` — `_ValidateFinding`, whose `__init__` at
  `:477` is `(layer, message, *, severity: str = "refusal")`. **`severity`
  already exists and already accepts `"advisory"`** — FR-010 needs no new
  machinery. Do not invent a third severity.
- `factory/cli/nouns/spec.py:923-960` — `_check_scenario_coverage`. The simplest
  existing check in shape: read a document, compare against parsed requirements,
  append findings, and at `:958` emit `severity="advisory"`. That line is
  FR-010's live worked example.
- `factory/cli/nouns/spec.py:1325-1409` — `_check_evidence`, signature
  `(spec_text, target_repo, findings, skipped, checked)`. **This is the shape to
  copy, not `_check_scenario_coverage`.** It is the only existing layer that
  takes the target repository, and it is the only one that models what your
  check must do when it cannot run: append to `skipped` with a reason and
  return, rather than reporting or passing.

**Three channels, and they are not interchangeable** (`:492`, `:496`, `:503`):

| list | what it means | reaches the exit code |
| --- | --- | --- |
| `findings` | a refusal or an advisory | **yes** — `:728` reads it alone |
| `information` | stated, never counted (044 FR-006, 106-US3) | no |
| `skipped` | the layer did not run, and why | no |

`has_refusal` / `has_advisory` are computed at `:673-674`; the advisory-only
sentence is `:690-694`; the exit code is `:728`,
`return EXIT_USER if has_refusal else EXIT_OK`. Anchor findings belong on
`findings`. An anchor check that could not run belongs on `skipped`.

**The layer must also register itself in two places, or the report lies:**

- `checked` (`:497-502`, appended at `:509`, `:612`, `:638` and inside
  `_check_evidence`) — the list of layers that actually ran.
- `factory/cli/nouns/spec.py:731-746` — `_all_pass_phrases`, which builds the
  "…all pass" sentence from a **hardcoded phrase list**. A layer added to
  `checked` but not given a phrase prints a clean bill of health that never
  names it. See trap 12.

**The fence mask FR-002 requires** — both citations verified exact:

- `factory/verify/criteria.py:189-219` — `mask_fences(lines) -> list[bool]`,
  flagging every line inside or delimiting a fenced block. Its module docstring
  at `:21-24` states why: "Real specs quote the template … a `- **FR-900**:`
  inside a fenced block is text about requirements, not a requirement." It is
  public precisely so other readers of authored documents can share it
  (`:62-63`). **Use it. Do not write a second fence scanner** — two fence
  scanners that disagree is a defect this repository has already paid for once.
- `factory/verify/criteria.py:122-163` — `parse_spec`, which calls `mask_fences`
  at `:129`. That call is the worked example of how to use it.

**Where the frontmatter boundary is:**

- A feature `spec.md` opens with `---` and its frontmatter closes at the
  **second** `---`. In `067-an-agent-can-start-on-any-host/spec.md` that is now
  line **122** (it was 73 in August — the hold note grew), and the citations
  above it are the anchors a review found broken, quoted as evidence. `plan.md`
  and `tasks.md` carry no frontmatter at all.

**A name already taken:** `factory/cli/nouns/spec.py:324` defines `_pick_anchor`,
which has nothing to do with this spec — it picks a tracked file for `spec new`
to scaffold against. Do not reuse or shadow that name.

## The measured scale, re-measured

Across every spec carrying anchors, counted 2026-09-01 with `mask_fences` applied
and `spec.md` frontmatter skipped — that is, counted the way FR-002 and FR-003
say to count:

| state | specs | anchors | broken | specs with a broken anchor |
| --- | --- | --- | --- | --- |
| landed | 100 | 3195 | 998 | 75 |
| draft | 15 | 412 | **89** | **11 of 15** |
| deferred | 1 | 0 | 0 | 0 |
| **total** | **116** | **3607** | **1087** | |

On 2026-08-20 the same count was 61 specs, 1624 anchors, 407 broken, and the
actionable set was **19 anchors in 6 specs**. It is now **89 anchors in 11 of
the 15 drafts** — a 4.7× growth in twelve days, from a factory doing nothing
unusual. The rot rate is the argument for the spec; it is not slowing.

Separately, counting only citations that name a symbol in the convention below,
across dispatchable specs: **21 such citations, 18 wrong** — 14 pointing outside
the named symbol's span, 2 naming a symbol that is not in the file, 2 naming a
file that no longer exists. The worst live miss is 636 lines. Three of the
eighteen were in this plan.

## Traps

**1. Skipping `spec.md` frontmatter is not a nicety — it is the difference
between a useful check and one that can never pass.** A held spec records the
broken anchors a review found, verbatim, as the evidence for why it was held.
067, 068 and 069 each carry several. A check that reports those makes every held
spec permanently unvalidatable, and the operator response will be to stop running
validate. FR-003 exists for this. US1-S5 is its test.

**2. Reuse `mask_fences`; do not regex for triple backticks.** Fences close only
on a run at least as long as the one that opened them, nested fences exist in
this repository's own specs, and `factory/verify/criteria.py:189-219` already
handles both. A second implementation will disagree with the first on some spec,
and the disagreement will surface as a criterion being parsed by one reader and
not the other.

**3. The bare `:NN` form is invisible to the obvious regex, and that is the whole
of US3.** A pattern keyed on `path.py:NN` will never see `` `:94` ``. Six existed
across 068 and 069, two inside traps instructing the implementer what *not* to
change — the most expensive possible place for a wrong line. US3 needs a
**stateful** scan that carries the last path seen forward. Decide and state what
"the same section" means: a markdown heading is the natural boundary, a bullet is
too narrow (068's traps 3 and 4 cite `:94` paragraphs away from the path).

**4. Use the AST for symbol spans, never a regex.** FR-007. `def _settle_answer`
appears in this repository inside a docstring and inside a comment as well as at
its definition. `ast.parse` plus `walk` gives `lineno`/`end_lineno` for every
`FunctionDef`, `AsyncFunctionDef` and `ClassDef` — that is the whole mechanism,
and it is a dozen lines. A regex will find the mention and report the wrong span,
which is worse than not checking.

Two shapes the walk must handle, both live in the corpus above: a dotted name
(`_ValidateFinding.__init__`) and a name defined more than once in one module. For
the dotted form, resolve the last segment and accept a span that nests inside the
first; for a duplicate name, a cited line inside **any** definition of that name
is not a finding — reporting a true citation is the failure mode this spec cannot
afford.

**5. A module cited forty times must be read once.** There are 3607 anchors
across 116 specs, many citing the same handful of large modules —
`factory/workgraph/workflow.py` is 4314 lines and is cited from dozens of specs.
Read into a dict keyed by path, and parse each module's AST at most once.
Validate is run interactively; a check that adds seconds will be turned off.

**6. Do not repair the 998 landed-spec anchors.** They are outside this spec.
They are also harmless: nothing dispatches from a landed spec again. FR-010 is
what keeps them reported-but-not-blocking, and a diff that "helpfully" fixes them
is a diff nobody can review.

**7. The control is the story, not a courtesy.** US1-S6 and US2-S2. A check that
reports every anchor passes SC-001 perfectly and is worthless. Both controls must
assert *silence* on a clean input, and the mutation to prove they can fail is to
break one anchor in the clean fixture and watch the control go red.

**8. Every fixture must be a SUPPLIED tree, never this repository.** The anchors
in `specs/` will move — that is the entire premise of this spec, and the table
above is the proof — so a test that asserts against real `factory/` line numbers
is a test that fails next week for the reason the spec exists. Build a tmp tree
with a known file and known lines.

**9. `validate` must stay usable on a spec with no `plan.md`.** Some feature
directories carry only `spec.md`. Absent documents are not findings.
`factory/cli/nouns/spec.py:749-760` — `_tasks_text` — is the shape: it returns
`None` for "not read", and its docstring states the rule this trap restates, that
a document nobody opened has no findings and calling that a clean bill of health
is how a check comes to be trusted for something it never did.

**10. Resolve cited paths against `--target-repo`, never against the process's
working directory.** `factory/cli/nouns/spec.py:131-135` gives validate a
`--target-repo` whose default is `/srv/factory/targets/short-links`, **which does
not exist on this host.** A check that resolves against `Path.cwd()` works
perfectly in the operator's shell and then behaves differently under the roadmap
and inside a node, which is the hardest class of defect this repository produces.
`_check_evidence` (`:1325-1409`) takes `target_repo` for exactly this reason —
take it the same way.

**11. When the target repository cannot be read, skip — do not report 3607
absent files.** This is trap 9's rule applied to trap 10's argument, and it is
the difference between a check that is adopted and one that is disabled in a
week. If `target_repo` is absent, or is a tree in which none of the cited paths
exist, append to `skipped` with a reason naming the path, and add nothing to
`findings`. FR-011, US1-S7.

**12. A new layer must be registered twice or the summary lies.** Append the
layer name to `checked`, *and* add its phrase to `_all_pass_phrases`
(`factory/cli/nouns/spec.py:731-746`). The all-pass sentence is built from a
hardcoded list, so a layer that runs, finds nothing, and is missing from that
list prints "frontmatter, work-graph derivation … all pass" while never telling
the operator the anchors were checked at all. The `fixes` phrase at `:744-745` is
the worked example of a conditionally-inserted layer.

**13. A citation is backticked; a mention is not — and this document depends on
it.** Look at the rot table at the top of this plan: the three dead anchors are
written *without* backticks, and so are the two in the spec's "what it costs"
section and the two in SC-004. That is deliberate. They are the spec's evidence,
they are wrong on purpose, and a check that keys on bare `path:NN` text would
refuse 072 on the strength of 072's own argument — along with every future
finding, decision record or hold note that quotes an anchor it is warning about.

Key the scan on the inline code span. It is the convention across all 116 specs,
it is how the 3607-anchor count was measured, and it is the only exit that works
mid-sentence — fences and frontmatter cover the block cases. When you write the
scanner, run it over `specs/072-a-stale-anchor-fails-validate-not-the-attempt/`
itself: **zero findings is the correct answer**, and any other answer means the
convention was not honoured.

**14. The judge sees the diff and the criteria — and Success Criteria are NOT
criteria.** `factory/verify/criteria.py` reads Success Criteria bullets past;
what reaches a judge is each story's acceptance scenarios and FR bullets. SC-001
through SC-004 are the operator's, not the gate's. Every Then-clause in the spec
is written "proven by a committed test" precisely so it *is* provable from the
diff.

## Sizing

Three small, fully independent stories; no story needs another's code.

US1 is a scan, a dict of file contents, and three failure kinds. Its difficulty
is entirely traps 1, 8, 10 and 11 — knowing what *not* to report, and against
which tree.

US2 is `ast.parse` plus a span lookup. Its difficulty is deciding the prose
convention for "this citation names a symbol", refusing to guess beyond it, and
trap 4's two shapes.

US3 is a stateful pass over the same scan US1 already does. Smallest of the three
if US1 is written with a reusable scanner; a rewrite if it is not.

## Verification the operator will run, independent of the gate

- **Prove US1 by control.** Validate a clean supplied spec — expect silence.
  Break one anchor in it, re-validate, expect exactly that one reported.
- **Prove US2 by mutation.** Point a symbol citation one line past its
  `end_lineno` and confirm the report; move it one line inside and confirm
  silence.
- **Prove the real case, and it no longer needs a reconstruction.** Restore this
  plan's own pre-2026-09-01 citations — `_validate_command` at :230-390,
  `_check_scenario_coverage` at :480-517 — validate, and confirm the check
  reports both. Those are not invented anchors; they are what this file said
  yesterday, and they are what US1 alone passes clean.
- **Prove trap 10.** Run validate with `--target-repo` pointing at a tree that
  does not contain the cited files, and confirm a skip with a reason rather than
  a wall of refusals.
