# Implementation Plan: a stale anchor fails validate, not the attempt

**Spec**: `specs/072-a-stale-anchor-fails-validate-not-the-attempt/spec.md`

## What already exists, and where

Every line below was read and **verified against `357d227` on 2026-08-20**. This
spec is about anchor rot, so an anchor in this plan that has rotted is an
embarrassment as well as a defect — check each before you rely on it.

**The validate command you are extending:**

- `factory/cli/nouns/spec.py:230-390` — `_validate_command`. It accumulates
  `_ValidateFinding` objects and its exit code reads that list alone. Your check
  appends to the same list; do not add a second reporting path.
- `factory/cli/nouns/spec.py:223-227` — `_ValidateFinding.__init__`, whose
  signature is `(layer, message, *, severity="refusal")`. **`severity` already
  exists and already accepts `"advisory"`** — FR-010 needs no new machinery, and
  `:347-348` is where the two are separated into exit codes. Do not invent a
  third severity.
- `factory/cli/nouns/spec.py:480-517` — `_check_scenario_coverage`, the closest
  existing check in shape: it reads `tasks.md`, compares against parsed spec
  requirements, and appends findings. **Copy its shape.** Your check is the same
  pattern over a different property.

**The fence mask FR-002 requires:**

- `factory/verify/criteria.py:189` — `mask_fences(lines) -> list[bool]`, flagging
  every line inside or delimiting a fenced block. Its module docstring at `:21-24`
  states why: "Real specs quote the template … a `- **FR-900**:` inside a fenced
  block is text about requirements, not a requirement." **It is public precisely
  so other readers of authored documents can share it** (`:62-63`).
  **Use it. Do not write a second fence scanner** — two fence scanners that
  disagree is a defect this repo has already paid for once.
- `factory/verify/criteria.py:122-163` — `parse_spec`, which calls `mask_fences`
  at `:129`. That call is the worked example of how to use it.

**Where the frontmatter boundary is:**

- A feature `spec.md` opens with `---`, and its frontmatter closes at the
  **second** `---` line. In `067-an-agent-can-start-on-any-host/spec.md` that is
  line 73, and the six citations above it are the hold note quoting the anchors a
  review found broken. `plan.md` and `tasks.md` carry no frontmatter at all.

## Traps

**1. Skipping `spec.md` frontmatter is not a nicety — it is the difference
between a useful check and one that can never pass.** A held spec records the
broken anchors a review found, verbatim, as the evidence for why it was held.
067, 068 and 069 each carry several. A check that reports those makes every
held spec permanently unvalidatable, and the operator response will be to stop
running validate. FR-003 exists for this. US1-S5 is its test.

**2. Reuse `mask_fences`; do not regex for triple backticks.** Fences close only
on a run at least as long as the one that opened them, nested fences exist in
this repo's own specs, and `factory/verify/criteria.py:189` already handles both. A second
implementation will disagree with the first on some spec, and the disagreement
will surface as a criterion being parsed by one reader and not the other.

**3. The bare `:NN` form is invisible to the obvious regex, and that is the whole
of US3.** A pattern keyed on `path.py:NN` will never see `` `:94` ``. Six existed
across 068 and 069, two inside traps instructing the implementer what *not* to
change — the most expensive possible place for a wrong line. US3 needs a
**stateful** scan that carries the last path seen forward. Decide and state what
"the same section" means: a markdown heading is the natural boundary, a bullet is
too narrow (068's traps 3 and 4 cite `:94` paragraphs away from the path).

**4. Use the AST for symbol spans, never a regex.** FR-007. `def _settle_answer`
appears in this repo inside a docstring and inside a comment as well as at its
definition. `ast.parse` plus `walk` gives `lineno`/`end_lineno` for every
`FunctionDef`, `AsyncFunctionDef` and `ClassDef` — that is the whole mechanism,
and it is a dozen lines. A regex will find the mention and report the wrong span,
which is worse than not checking.

**5. Cache file reads, or this check is the slowest thing in validate.** There
are **1624 anchors across 61 specs**, many citing the same handful of large
modules. Reading the file per anchor re-reads `factory/workgraph/workflow.py`
(2700+ lines) dozens of times per spec. Read once into a dict keyed by path.
Measure it; validate is run interactively and a check that adds seconds will be
skipped.

**6. Do not repair the 388 landed-spec anchors.** They are outside this spec.
They are also harmless: nothing dispatches from a landed spec again. FR-010 is
what keeps them reported-but-not-blocking, and a diff that "helpfully" fixes them
is a diff nobody can review.

**7. The control is the story, not a courtesy.** US1-S6 and US2-S2. A check that
reports every anchor passes SC-001 perfectly and is worthless. Both controls must
assert *silence* on a clean input, and the mutation to prove they can fail is to
break one anchor in the clean fixture and watch the control go red.

**8. Every fixture must be a SUPPLIED tree, never this repository.** The anchors
in `specs/` will move — that is the entire premise of this spec — so a test that
asserts against real `factory/` line numbers is a test that fails next week for
the reason the spec exists. Build a tmp tree with a known file and known lines.

**9. `validate` must stay usable on a spec with no `plan.md`.** Some feature
directories carry only `spec.md`. Absent documents are not findings.

**10. One test file per story, named here.**
- US1 → `tests/test_anchor_resolution.py`
- US2 → `tests/test_anchor_names_its_symbol.py`
- US3 → `tests/test_bare_line_references.py`

**11. The judge sees the diff and the criteria — and Success Criteria are NOT
criteria.** `factory/verify/criteria.py` reads Success Criteria bullets past;
what reaches a judge is each story's acceptance scenarios and FR bullets. SC-001
through SC-004 are the operator's, not the gate's. Every Then-clause above is
written "proven by a committed test" precisely so it *is* provable from the diff.

## Sizing

Three small, fully independent stories; no story needs another's code.

US1 is a scan, a dict of file contents, and three failure kinds. Its difficulty
is entirely trap 1 and trap 8 — knowing what *not* to report.

US2 is `ast.parse` plus a span lookup. Its difficulty is deciding the prose
convention for "this citation names a symbol" and refusing to guess beyond it.

US3 is a stateful pass over the same scan US1 already does. Smallest of the three
if US1 is written with a reusable scanner; a rewrite if it is not.

## Verification the operator will run, independent of the gate

- **Prove US1 by control.** Validate a clean supplied spec — expect silence.
  Break one anchor in it, re-validate, expect exactly that one reported.
- **Prove US2 by mutation.** Point a symbol citation one line past its
  `end_lineno` and confirm the report; move it one line inside and confirm
  silence.
- **Prove the real case.** Restore `_judge_rewrites_spent` to `:127-145` in a
  copy of 068's plan, validate, and confirm the check reports it — that is the
  fifty-four line miss this spec exists to have caught.
