---
state: ready
depends_on_landed: [104-install-brings-the-container-up-configured]
# DRAFTED 2026-08-23 ~10:25 PM CT by the operator session behind
# docs/container-onramp-program.md. REPAIRED 2026-08-24 against an adversarial
# review: US1 split on the seam the plan already named, the readiness-renderer
# change split out of the install story, and the 104 collision declared rather
# than asserted away. Evidence: findings §7 (scaffolds, command collapsing,
# install endings) and the operator memory that a CLI welcome journey must
# stay skippable.
#
# `depends_on_landed: [104]` is a REAL edge, not a formality. 104's T035
# rewrites the body of `install_command` around
# `factory/cli/install.py:687-724`, and this spec's US6 inserts its closing
# step into that same block. Raced, whichever lands second is a textually
# clean merge that is semantically wrong — the class this repository already
# paid for once (`factory/cli/init.py:124-127`: two concurrent stories each
# added a factory to one file in different regions, nothing conflicted, the
# merge kept both and nine tests died). The roadmap dispatches a `ready` spec
# on its own schedule, so a prose note reaches no scheduler and this edge is
# the only mechanism that holds. An operator who would rather sequence by hand
# deletes this line — knowingly.
#
# 105 also co-tenants `factory/cli/nouns/build.py` with US4 here (105's T026
# pins `_cli_revision` at :741 and `_skew_notice` at :761 byte-identical, its
# T028 adds a call at :316; US4 declares a new `ship` subparser near :1522).
# The regions are far apart and neither story renames or moves the other's,
# so no edge is drawn — but every `build.py` anchor in plan.md is stale the
# moment 105 lands, which is why the plan says to re-open each one.
#
# Settled at drafting:
#   - The scaffold is a FADED WORKED EXAMPLE, not an empty template: one
#     tiny fully-worked story whose file:line anchor is picked from the real
#     target tree at scaffold time, later slots progressively skeletal,
#     every mandatory blank a grep-able `ERGANE-TODO:` sentinel. The
#     worked-example effect is among the most replicated results in learning
#     science (findings §7); sqlc/alembic's empty scaffolds are the
#     anti-pattern, dbt's green-on-first-run is the pattern.
#   - Sentinels make the scaffold VALID BUT NOT DISPATCHABLE: `spec
#     validate` accepts the structure and reports each sentinel with
#     file:line as "not ready to derive"; `spec derive` refuses while any
#     remain. The first validate teaches; the no-vacuous-green ethos holds.
#   - The pipeline verb is a SUPERSET THAT PAUSES, terraform-shaped:
#     validate → derive stream their full labeled output, then the compiled
#     graph summary, then a confirmation BEFORE dispatch — because dispatch
#     spends real money and the pause is structurally where pre-dispatch
#     refinement lives. `--yes` for automation. The three constituent verbs
#     survive untouched (factory/cli/nouns/spec.py:89-187 is the surface;
#     start_command at factory/cli/nouns/build.py:571).
#   - Install ends by DOING something free, local and skippable — never a
#     dispatch (fly's accidental-Postgres billing threads are the cautionary
#     tale; dispatch is Ergane's money step).
---

# Feature Specification: a first spec scaffolds, validates and ships

**Created**: 2026-08-23

## The gap, stated precisely

The unit of work is a document the developer has to write — three of them —
and the onramp currently hands over no scaffold (`ergane --help` has no
`spec new`), then asks for three commands (`spec validate`, `spec derive`,
`build start`) to turn the finished document into motion. The measured
leverage of this factory is in refinement before dispatch; the current verb
grammar neither teaches a newcomer what a good spec looks like nor gives the
practiced operator a single motion that preserves the review pause.

## The rule this spec is asking for

**`ergane spec new` produces a spec that passes validate as generated and
cannot dispatch as generated; `ergane build ship` collapses
validate → derive → confirm → start into one verb without hiding a single
stage's output; and install ends mid-conversation — a scaffolded example
taken through validate and derive, and the next command printed — never at a
"ready" banner and never at a dispatch.**

## User Scenarios & Testing

### User Story 1 - The scaffold generator emits a trio that validates (Priority: P1)

As a developer reading my first scaffold, the text itself teaches me: one
worked story I can imitate, blanks I cannot miss, and a document the factory's
own validator already accepts.

**Acceptance Scenarios**:

1. **Given** a slug, a title and an already-resolved `path:line` anchor,
   **When** the generator runs, **Then** it returns three texts — one fully
   worked story, one partial, one skeletal — whose story headings, literal
   Given/When/Then acceptance scenarios, `## Work Graph` fence with an
   explicit `implements:` on every node, and `state: draft` frontmatter are
   all present, with an `ERGANE-TODO:` sentinel on every mandatory blank and
   no sentinel inside a story heading, the Work Graph fence, or a task id —
   proven by committed tests that parse the returned text rather than diff a
   golden file.
2. **Given** that returned trio written to a directory, **When** the real
   `ergane spec validate` runs over it, **Then** it exits 0 with no refusal
   and no scenario-coverage advisory, every compiled node's task slice
   resolves, and the generated stories name no file in common with each other
   — proven by a committed transcript and committed tests.
3. **Given** the generator's demonstration mode, **When** it runs, **Then** it
   returns the worked story alone with no sentinel and no skeletal slot, so
   the result derives cleanly — proven by a committed test.

### User Story 2 - `ergane spec new` numbers, anchors and writes atomically (Priority: P1)

As a developer, one command puts that scaffold on disk under a number nobody
else owns, with an anchor that really resolves — or it writes nothing at all.

**Acceptance Scenarios**:

1. **Given** a specs root already holding numbered directories, **When**
   `ergane spec new <slug>` chooses a number, **Then** it is the next free
   one, counting every numbered directory whatever it contains, never reusing
   one already taken, and refusing rather than guessing when two directories
   claim the same number — proven by committed tests.
2. **Given** a target repository, **When** the worked story's anchor is
   chosen, **Then** it names a tracked file in that repository with at least
   that many lines, read back to confirm it resolves; and **Given** a
   repository offering no eligible file, **Then** the command refuses naming
   what it looked for rather than emitting an unresolvable anchor — proven by
   committed tests.
3. **Given** the pre-rename self-proof fails, **When** the command returns,
   **Then** the specs root has gained no directory and no temporary residue —
   proven by a committed test.
4. **Given** generation completes, **When** the command ends, **Then** it
   prints the created directory and the exact next command; **Given** the
   persona registry cannot answer for the persona the deriver will name,
   **Then** that same block also names `ergane install` — proven by committed
   tests and a committed transcript.

### User Story 3 - Sentinels gate derive, not validate (Priority: P1)

As the validator, I accept the scaffold's structure and refuse to compile
its blanks.

**Acceptance Scenarios**:

1. **Given** a fresh scaffold, **When** `spec validate` runs, **Then**
   structure passes and each sentinel is listed with file:line as "not
   ready to derive" — proven by a committed test.
2. **Given** remaining sentinels, **When** `spec derive` runs, **Then** it
   refuses naming each; **Given** none remain, **Then** derive proceeds
   unchanged — both proven by committed tests.

### User Story 4 - `build ship` collapses without hiding (Priority: P1)

As a practiced operator, one verb takes a finished spec to dispatch —
showing me every stage and pausing where my judgement belongs.

**Acceptance Scenarios**:

1. **Given** a valid spec, **When** `ergane build ship <dir>` runs, **Then**
   validate's and derive's full labeled output stream in order, the
   compiled-graph summary prints (story count, order, and for every node both
   its persona and the model alias the persona registry resolves for it, never
   a blank), and a confirmation gates dispatch with `--yes` to skip —
   dispatch stubbed, proven by committed tests.
2. **Given** a validate failure, **When** ship runs, **Then** it stops at
   that stage with that stage's full output and no dispatch.
3. **Given** the three constituent verbs, **When** their existing tests
   run, **Then** they pass unmodified.

### User Story 5 - Every non-passing readiness line names its fix (Priority: P2)

As an operator reading a readiness report, a line that is not green tells me
the command that clears it, instead of leaving me to guess.

**Acceptance Scenarios**:

1. **Given** a repository profile carrying one blocking and one warning
   finding and a supplied remedy table, **When** the readiness report renders,
   **Then** every non-passing line carries a runnable fix clause, and a check
   name the table does not know falls back to a stated line naming
   `ergane init --check` rather than to silence — proven by committed tests.
2. **Given** no remedy table is supplied, **When** the same report renders,
   **Then** its text is byte-identical to what it renders today, so
   `ergane init --check` and its existing tests are unchanged — proven by a
   committed test and by the existing suite green in the diff.

### User Story 6 - Install ends mid-conversation (Priority: P2)

As a new operator, install's last words are a working demonstration and my
next command — not a banner.

**Acceptance Scenarios**:

1. **Given** a completed install, **When** the closing step runs, **Then**
   a readiness pass prints with every red line naming its fixing command,
   reusing the findings install has already computed rather than probing a
   second time; a throwaway spec in a temporary repository goes through
   scaffold + validate + derive with the compiled graph shown; nothing is
   dispatched, nothing is registered, no schedule is published, and the
   transcript ends with the verbatim next command — proven through injected
   seams, with committed transcripts.
2. **Given** the operator skips, **When** the skip is chosen, **Then**
   install ends cleanly with the same next command printed — skippable is
   part of the contract.

## Work Graph

```yaml
US1:
  implements: []
  depends_on: []
US2:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US3:
  implements: []
  depends_on: []
  depends_on_merged: [US1]
US4:
  implements: []
  depends_on: []
US5:
  implements: []
  depends_on: []
US6:
  implements: []
  depends_on: []
  depends_on_merged: [US1, US3, US5]
```

## Requirements (summary — numbered at refinement)

Numbering from the specs root's next free number (landed story numbers are
immutable; spec numbers follow the same discipline); anchor selection must
verify the chosen file:line resolves at scaffold time; sentinel grammar and
its validate/derive semantics; ship's stage streaming, failure stop,
summary content — including a resolved model alias per node, never a blank —
pause and `--yes`; constituent verbs behaviourally unchanged (their existing
tests pass unmodified); the readiness renderer grows an optional remedy table
and is byte-identical without one; the smoke is skippable, probes nothing a
second time, prints its cleanup, and leaves nothing registered; every path
ends by printing the next command.

## Success Criteria (summary)

Pasted: the generator's own output taken through a real validate run showing
structural acceptance; a scaffold's validate run showing the sentinel list;
derive refusing on the same scaffold; the completed example shipping through
`build ship` with all three stages' output, a graph summary whose every line
carries a resolved model alias, and the pause visible; the readiness report
with a remedied red line; the install smoke transcript ending in the printed
next command.
Operator verification: hand `ergane spec new` to a real first-time developer
(or the operator cold) and watch whether the first validate teaches or
punishes — the scaffold's whole purpose, and the one thing a gate cannot
measure.
