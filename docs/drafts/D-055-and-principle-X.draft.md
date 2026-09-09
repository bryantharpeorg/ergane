<!-- DRAFT for operator review. Two changes, one amendment:
       (1) append D-055 to docs/decisions.md
       (2) add Principle X to .specify/memory/constitution.md
       (3) bump the constitution to 2.8.0 and extend the Last Amended note
     Not committed by the drafting session; the decision log and the constitution
     are operator-promoted, per the Governance section. -->

# Proposed: Principle X — A Citation Is Resolved By Its Symbol

## Why this is being promoted now

`refinement/a-landing-silently-invalidates-every-spec-anchor-below-it` reached
**four occurrences** on 2026-09-08, past the promotion bar of three. The sibling
row `refinement/the-symbol-anchor-tier-only-fires-on-a-prose-convention-the-existing-corpus-does-not-use`
is at two. Both are the same mechanism seen from different ends, and neither is
fixable by tooling alone — which is what makes it a principle rather than a bug.

## The text to add, after Principle IX

### X. A Citation Is Resolved By Its Symbol

A spec, plan or task cites the tree in the form `path/to/file.py:NN` — `symbol`.
**The symbol governs. The line number is a hint that was true when it was
written.**

An agent that meets a citation whose line no longer holds the symbol it names
works from the symbol, and says so in its pull request body. It does not edit
whatever happens to occupy that line, and it does not silently hunt for what the
author might have meant. Where the symbol cannot be found in the named file at
all, the agent **refuses and names the citation it could not resolve** — the same
refusal Principle IX requires of an absent declaration, for the same reason.

This is not a courtesy to sloppy authorship. Line numbers in this repository rot
by construction: the factory lands into the files its own specs cite, and a spec
refined on Tuesday is dispatched against a Wednesday tree. On 2026-09-08 a single
merge added 111 lines to `factory/roadmap/workflow.py` and moved **all 128** of
one spec's citations of that file; `ergane spec validate` went from zero refusals
to forty-five on a document nobody had edited. Earlier the same day, an
`ast`-based sweep of four specs found **52 citations that named a symbol they fell
outside of**, every one of which the validator had just passed — its symbol check
binds only when the path and the symbol sit on the same line, and markdown wraps.
The worst named `_query_status` and pointed a hundred and twenty lines away, at an
unrelated function's definition. A refinement pass over spec 057 found fifteen of
sixteen citations had moved, and the validator refused exactly one.

So an agent cannot be told to trust the numbers, and tooling cannot be relied on
to have checked them. What can be relied on is the name: a symbol that has been
renamed or deleted is a fact worth stopping for, and a symbol that has merely
moved is one the agent can find. Reading the citation the other way round — number
first — converts every landing into a silent hazard for every spec beneath it, and
the cost lands on an implementer who had no way to know.

**For whoever writes the citation**: this principle is what makes the `— symbol`
suffix load-bearing rather than decorative. A bare `path:NN` carries no name for
the reader to fall back on, and is therefore a citation that cannot be repaired
by anyone but its author.

## The decision-log entry to append

## D-055 · A citation is resolved by its symbol; the line number is a hint (decided)

Decided 2026-09-08, after `refinement/a-landing-silently-invalidates-every-spec-anchor-below-it`
reached four occurrences.

1. **The rot is structural, not editorial.** This factory lands into the files its
   own specs cite. A spec is refined against one tree and dispatched against
   another, and nothing between those two moments tells the operator that the
   coordinates have moved. Measured 2026-09-08: one merge moved 128 of one spec's
   citations and took it from 0 to 45 validate refusals with no edit to the
   document.

2. **Tooling cannot close it, and appearing to close it is worse.** 072's symbol
   check is real but binds only when path and symbol share a line; markdown wraps
   at eighty columns, so the common case is unchecked. Four specs that reported
   **zero refusals** carried 52 citations pointing outside the symbol they named.
   A green validate is a check on the paths, not on the anchors, and an operator
   who reads it as the latter ships a spec that will send an agent hunting.

3. **The rule is therefore about reading, not about writing.** Authors will keep
   producing stale numbers no matter how careful they are, because the staleness
   is created after they finish. What can be made reliable is how the number is
   *read*: symbol first, line as a hint, refusal when the symbol is gone.

4. **What this does not do.** It does not excuse an author from re-anchoring
   before dispatch — that remains the refinement duty, and re-validating
   immediately before a flip rather than at the end of a pass is the operator
   practice this entry assumes. It changes what an agent does when the duty was
   imperfectly discharged, which on the evidence is always.

Supersedes nothing. Widens Principle IX's refusal-over-fallback rule from values
a program reads to coordinates an agent reads.

## The version line to replace

**Version**: 2.8.0 | **Ratified**: 2026-07-24 | **Last Amended**: 2026-09-08 (2.8.0 —
D-055: Principle X added; a citation is resolved by the symbol it names, the line
number is a hint, and a symbol that cannot be found is refused rather than guessed
at. 2.7.0 — [existing text continues unchanged])
