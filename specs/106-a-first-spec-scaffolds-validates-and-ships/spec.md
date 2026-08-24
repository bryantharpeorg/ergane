---
state: draft
# DRAFTED 2026-08-23 ~10:25 PM CT by the operator session behind
# docs/container-onramp-program.md. Spec-only draft: plan.md and tasks.md at
# refinement. Independent of 088/103/104/105 except US4's full effect, which
# wants 103+104 landed. Evidence: findings §7 (scaffolds, command
# collapsing, install endings) and the operator memory that a CLI welcome
# journey must stay skippable.
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

### User Story 1 - `ergane spec new` scaffolds a faded worked example (Priority: P1)

As a developer writing my first spec, the scaffold teaches me by example:
one worked story I can imitate, blanks I cannot miss, and the next command
printed.

**Acceptance Scenarios**:

1. **Given** a target repo, **When** `ergane spec new <slug>` runs, **Then**
   the trio is created under the next free number with one fully-worked
   story whose file:line anchor resolves in that repo (checked at scaffold
   time), one illustrative trap, progressively skeletal later slots, and an
   `ERGANE-TODO:` sentinel on every mandatory blank — proven by committed
   tests against a fixture repo.
2. **Given** generation completes, **When** the command ends, **Then** it
   prints the exact next command.
3. **Given** existing spec numbers, **When** the number is chosen, **Then**
   it is the next free one and never reuses any — numbers are immutable.

### User Story 2 - Sentinels gate derive, not validate (Priority: P1)

As the validator, I accept the scaffold's structure and refuse to compile
its blanks.

**Acceptance Scenarios**:

1. **Given** a fresh scaffold, **When** `spec validate` runs, **Then**
   structure passes and each sentinel is listed with file:line as "not
   ready to derive" — proven by a committed test.
2. **Given** remaining sentinels, **When** `spec derive` runs, **Then** it
   refuses naming each; **Given** none remain, **Then** derive proceeds
   unchanged — both proven by committed tests.

### User Story 3 - `build ship` collapses without hiding (Priority: P1)

As a practiced operator, one verb takes a finished spec to dispatch —
showing me every stage and pausing where my judgement belongs.

**Acceptance Scenarios**:

1. **Given** a valid spec, **When** `ergane build ship <dir>` runs, **Then**
   validate's and derive's full labeled output stream in order, the
   compiled-graph summary prints (story count, order, personas), and a
   confirmation gates dispatch with `--yes` to skip — dispatch stubbed,
   proven by committed tests.
2. **Given** a validate failure, **When** ship runs, **Then** it stops at
   that stage with that stage's full output and no dispatch.
3. **Given** the three constituent verbs, **When** their existing tests
   run, **Then** they pass unmodified.

### User Story 4 - Install ends mid-conversation (Priority: P2)

As a new operator, install's last words are a working demonstration and my
next command — not a banner.

**Acceptance Scenarios**:

1. **Given** a completed install, **When** the closing step runs, **Then**
   a doctor-style pass prints with every red line naming its fixing
   command, a throwaway spec in a temporary repo goes through
   init + validate + derive with the graph shown, nothing is dispatched,
   nothing stays registered, and the transcript ends with the verbatim next
   command — proven through seams.
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
US4:
  implements: []
  depends_on: []
  depends_on_merged: [US1, US2]
```

## Requirements (summary — numbered at refinement)

Numbering from the specs root's next free number (landed story numbers are
immutable; spec numbers follow the same discipline); anchor selection must
verify the chosen file:line resolves at scaffold time; sentinel grammar and
its validate/derive semantics; ship's stage streaming, failure stop,
summary content, pause and `--yes`; constituent verbs behaviourally
unchanged (their existing tests pass unmodified); the smoke is skippable,
prints its cleanup, and leaves nothing registered; every path ends by
printing the next command.

## Success Criteria (summary)

Pasted: a scaffold's validate run showing structural acceptance plus the
sentinel list; derive refusing on the same scaffold; the completed example
shipping through `build ship` with all three stages' output and the pause
visible; the install smoke transcript ending in the printed next command.
Operator verification: hand `ergane spec new` to a real first-time developer
(or the operator cold) and watch whether the first validate teaches or
punishes — the scaffold's whole purpose, and the one thing a gate cannot
measure.
