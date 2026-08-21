---
state: draft
# Drafted 2026-08-20 6:45 AM CT by an operator session, immediately after a
# re-review of 067/068/069 corrected 34 broken anchors that `ergane spec
# validate` had passed clean every single time it was run on them.
#
# Filed first as
# `verify/spec-validate-never-resolves-a-file-line-anchor-so-the-largest-refinement-defect-class-is-unchecked`
# (critical). This spec is that finding's fix.
#
# DO NOT FLIP READY without a pre-dispatch review. That rule is what produced
# this spec.
---

# Feature Specification: a stale anchor fails validate, not the attempt

**Created**: 2026-08-20

## The gap, stated precisely

A plan cites the tree by `file.py:NN`. An implementer is dispatched with that
citation and opens it. When the line has moved, the implementer lands in the
middle of a docstring, or on a closing paren, or inside a different function
with a plausible name — and the failure does not announce itself. It presents as
an agent that "did not follow the plan".

`ergane spec validate` runs six checks — frontmatter, work-graph derivation,
persona registry, scenario coverage, prompt assembly, slice coverage. **Not one
of them opens a file the plan cites.** A spec whose every anchor is stale
validates clean.

### This is not a drafting-discipline problem

The tempting reading is that drafters are careless. Measured, that reading is
wrong. On 2026-08-19 three specs were written with anchors that were **correct
when written**. Overnight the factory landed 070/US5, 071/US1, 071/US2 and
070/US3 into `factory/verify/ladder.py`, `factory/verify/models.py`,
`factory/workgraph/adapter.py` and `factory/activities/agent_activities.py` —
four of the files those specs cite. By morning 34 anchors were wrong.

**The factory staled its own specs by shipping.** No amount of care at drafting
time prevents that, because the rot happens after drafting. Only a check that
runs at validate time can catch it.

### What it costs when it is not caught

`_judge_rewrites_spent` was cited at `:127-145`. It is at `:181-199` — a
fifty-four line miss, and it is the function the whole of 068/US1 turns on. The
line the plan pointed at is inside a *different* function's body, which reads as
real code. An implementer would have edited the wrong function and the diff would
have looked reasonable.

Worse, one citation named `_settle_answered`, which **does not exist** — the
function is `_settle_answer`. That is not a moved line; it is a symbol that was
never there, and nothing in the pipeline noticed.

### The measured scale

Across all 61 specs carrying anchors: **1624 anchors, 407 broken.** But the
distribution is what makes this fixable rather than hopeless:

| state | specs | anchors | broken |
| --- | --- | --- | --- |
| landed | 49 | 1295 | 388 |
| ready | 4 | 214 | 5 |
| draft | 8 | 115 | 14 |

A landed spec's rot is harmless — nothing dispatches from it again. **The
actionable set is nineteen anchors in six specs**, and five of those are in a
spec that is already complete. A refusal scoped to specs that can still dispatch
has a blast radius of six, not forty-five.

## User Scenarios & Testing

### User Story 1 - An anchor that does not resolve is named before dispatch (Priority: P1)

As an operator, `ergane spec validate` tells me which citations in a plan no
longer point at code, so I fix them at refinement instead of paying for them at
dispatch.

**Why this priority**: P1 and independently useful with nothing else in this
spec. It is the tier that would have caught most of the thirty-four.

**Acceptance Scenarios**:

1. **Given** a plan citing a line number past the end of the file it names,
   **When** the spec is validated, **Then** the report names that citation, its
   file, and the line it was found on — proven by a committed test over a
   supplied tree.
2. **Given** a plan citing a line that exists but is blank, **When** the spec is
   validated, **Then** it is reported — proven by a committed test. A blank line
   is the signature of a deleted anchor and is never a deliberate citation.
3. **Given** a plan citing a file that does not exist, **When** the spec is
   validated, **Then** it is reported naming the path — proven by a committed
   test.
4. **Given** a citation inside a fenced code block, **When** the spec is
   validated, **Then** it is **not** reported — specs quote the template, and a
   citation inside a fence is text about a citation. Proven by a committed test.
5. **Given** a citation inside `spec.md`'s frontmatter comment block, **When**
   the spec is validated, **Then** it is **not** reported. Held specs quote their
   own broken anchors deliberately, as the record of what a review found; a check
   that flags those makes every held spec permanently unvalidatable. Proven by a
   committed test.
6. **Given** a plan whose every anchor resolves, **When** the spec is validated,
   **Then** nothing is reported — proven by a committed test. This is the control
   for scenarios 1 to 3.

### User Story 2 - An anchor that lands on the wrong symbol is named (Priority: P1)

As an operator, a citation that names a function and points somewhere else is
reported, because that is the failure that reads as real code and costs the
attempt.

**Why this priority**: P1. It is the tier that catches the fifty-four line miss
and the function that does not exist — the two that would have cost the most.

**Acceptance Scenarios**:

1. **Given** a citation written as `` `path.py:NN` — `symbol_name` `` where `NN`
   falls outside that symbol's definition, **When** the spec is validated,
   **Then** it is reported naming the symbol, the cited line, and the line range
   the symbol actually occupies — proven by a committed test.
2. **Given** the same citation where `NN` falls **inside** the symbol's
   definition, **When** the spec is validated, **Then** nothing is reported —
   proven by a committed test. This is the control.
3. **Given** a citation naming a symbol that does not exist in the cited file,
   **When** the spec is validated, **Then** it is reported as an absent symbol
   rather than as a line mismatch, because the two are different repairs —
   proven by a committed test.
4. **Given** a citation with no symbol name in its prose, **When** the spec is
   validated, **Then** only US1's resolution check applies and no symbol claim is
   invented — proven by a committed test.

### User Story 3 - A bare line reference is resolved or refused (Priority: P2)

As an operator, a citation written as `` `:NN` `` with no filename is checked
against the file its surrounding block names, or reported as unanchorable.

**Why this priority**: P2 and it depends on nothing. These are invisible to a
filename-based sweep — six existed across 068 and 069, two of them in traps
telling the implementer what not to change.

**Acceptance Scenarios**:

1. **Given** a bullet citing `` `factory/verify/ladder.py:68-105` `` and later
   `` `:94` ``, **When** the spec is validated, **Then** `:94` is resolved
   against `factory/verify/ladder.py` and checked as in US1 — proven by a
   committed test.
2. **Given** a bare `` `:NN` `` with no filename cited anywhere before it in the
   same section, **When** the spec is validated, **Then** it is reported as
   unanchorable rather than silently skipped — proven by a committed test.
3. **Given** a bare reference that resolves to a blank line, **When** the spec is
   validated, **Then** it is reported exactly as US1 would report it — proven by
   a committed test.
4. **Given** a document with no bare references at all, **When** the spec is
   validated, **Then** nothing is reported and US1's behaviour is unchanged —
   proven by a committed test.

## Requirements

- **FR-001**: `ergane spec validate` MUST open every `path:NN` and `path:NN-MM`
  citation appearing in the feature's `spec.md` body, `plan.md` and `tasks.md`,
  and MUST report each one whose file is absent, whose line is past end-of-file,
  or whose line is blank. All three documents reach an implementer, and 068's
  `spec.md` carried five broken citations of its own.
- **FR-002**: The check MUST skip citations inside fenced code blocks, reusing
  the fence mask the criteria parser already applies rather than a second scan.
- **FR-003**: The check MUST skip citations inside `spec.md`'s frontmatter,
  because a held spec records its own broken anchors deliberately.
- **FR-004**: A report MUST name the citing document and line, the cited path and
  line, and which of the three failure kinds it is.
- **FR-005**: A range citation `NN-MM` MUST be checked at both endpoints, and MUST
  be reported when `MM` precedes `NN`.
- **FR-006**: When a citation's prose names a Python symbol, the check MUST
  resolve that symbol's definition span and MUST report a cited line falling
  outside it.
- **FR-007**: Symbol spans MUST be resolved from the module's parsed syntax tree,
  never by regular expression, so a name appearing in a comment or a string is
  not mistaken for a definition.
- **FR-008**: A named symbol absent from the cited file MUST be reported as an
  absent symbol, distinctly from a line-outside-span report.
- **FR-009**: A bare `:NN` citation MUST be resolved against the most recent path
  cited before it within the same section, and MUST be reported as unanchorable
  when no such path exists.
- **FR-010**: Anchor findings MUST be a refusal for a spec whose state can still
  dispatch, and an advisory otherwise, so that the 388 broken anchors in landed
  specs do not turn every validate into a failure.

## Work Graph

```yaml
US1:
  depends_on: []
  implements: [FR-001, FR-002, FR-003, FR-004, FR-005, FR-010]
US2:
  depends_on: []
  implements: [FR-006, FR-007, FR-008]
US3:
  depends_on: []
  implements: [FR-009]
```

## Success Criteria

- **SC-001**: Run `ergane spec validate` against a supplied spec whose anchors are
  deliberately stale, and paste the report. Every stale anchor must appear.
- **SC-002**: Run it against a spec whose anchors all resolve and paste the
  report. Nothing must appear. Without this control SC-001 is satisfied by a
  check that reports everything.
- **SC-003**: Run it across every spec in `specs/` and paste the per-state
  totals. The landed tier must be advisory and the ready/draft tier a refusal.
- **SC-004**: Paste a before-and-after of one real repair — the `:127-145` to
  `:181-199` correction for `_judge_rewrites_spent` — showing the check reporting
  it and then falling silent.

## Assumptions

- Anchors cite Python. Markdown, YAML and SQL citations exist in the tree but are
  rarer and carry no symbol claim; FR-001 covers them by line, FR-006 does not
  attempt symbols for them.
- The symbol-in-prose convention is `` `path.py:NN` — `symbol` `` or
  `` `path.py:NN` -- `symbol` ``. Where a plan states the symbol some other way,
  US2 will not fire, and US1 still applies. Widening the convention is not in
  scope.
- The 388 broken anchors in landed specs are not repaired by this spec. They are
  harmless — nothing dispatches from a landed spec — and FR-010 exists so they
  stay reported without blocking.
